package study;

import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

import com.github.skjolber.packing.api.Box;
import com.github.skjolber.packing.api.BoxItem;
import com.github.skjolber.packing.api.BoxStackValue;
import com.github.skjolber.packing.api.Container;
import com.github.skjolber.packing.api.ContainerItem;
import com.github.skjolber.packing.api.Packager;
import com.github.skjolber.packing.api.PackagerResult;
import com.github.skjolber.packing.api.PackagerResultBuilder;
import com.github.skjolber.packing.api.Placement;
import com.github.skjolber.packing.packer.laff.LargestAreaFitFirstPackager;
import com.github.skjolber.packing.packer.plain.PlainPackager;
import com.github.skjolber.packing.packer.bruteforce.FastBruteForcePackager;

public class SkjolberThpackCampaign {

    private static final Set<Integer> MALFORMED = Set.of(18, 19, 20);
    private static final String[] ROTATIONS = {
            "ROTATION_XYZ", "ROTATION_YXZ", "ROTATION_ZYX",
            "ROTATION_YZX", "ROTATION_XZY", "ROTATION_ZXY"
    };

    private record ItemSpec(String id, int x, int y, int z, int copies, Set<String> rotations) {}
    private record Instance(String sourceId, int number, Path items, Path bins) {}
    private record Validation(List<String> errors, int placements, long packedVolume, long binVolume) {}

    private static Map<String, String> csvRow(String header, String row) {
        String[] keys = header.split(",", -1);
        String[] values = row.split(",", -1);
        if (keys.length != values.length) {
            throw new IllegalArgumentException("CSV column mismatch: " + row);
        }
        Map<String, String> result = new HashMap<>();
        for (int i = 0; i < keys.length; i++) {
            result.put(keys[i], values[i]);
        }
        return result;
    }

    private static List<Map<String, String>> readCsv(Path path) throws IOException {
        List<String> lines = Files.readAllLines(path, StandardCharsets.UTF_8);
        List<Map<String, String>> rows = new ArrayList<>();
        for (int i = 1; i < lines.size(); i++) {
            if (!lines.get(i).isBlank()) {
                rows.add(csvRow(lines.get(0), lines.get(i)));
            }
        }
        return rows;
    }

    private static Set<String> permittedRotations(Map<String, String> row) {
        Set<String> rotations = new HashSet<>();
        for (String rotation : ROTATIONS) {
            if ("1".equals(row.get(rotation))) {
                rotations.add(rotation.substring("ROTATION_".length()));
            }
        }
        return rotations;
    }

    private static String rotationName(ItemSpec item, BoxStackValue value) {
        int[] original = {item.x(), item.y(), item.z()};
        int[] placed = {value.getDx(), value.getDy(), value.getDz()};
        int[][] indexes = {{0, 1, 2}, {1, 0, 2}, {2, 1, 0}, {1, 2, 0}, {0, 2, 1}, {2, 0, 1}};
        for (int i = 0; i < indexes.length; i++) {
            int[] order = indexes[i];
            if (placed[0] == original[order[0]] && placed[1] == original[order[1]]
                    && placed[2] == original[order[2]] && item.rotations().contains(ROTATIONS[i].substring(9))) {
                return ROTATIONS[i].substring(9);
            }
        }
        return null;
    }

    private static BoxItem boxItem(ItemSpec item) {
        Box allRotations = Box.newBuilder()
                .withId(item.id())
                .withSize(item.x(), item.y(), item.z())
                .withWeight(0)
                .withRotate3D()
                .build();
        List<BoxStackValue> selected = new ArrayList<>();
        for (BoxStackValue value : allRotations.getStackValues()) {
            if (rotationName(item, value) != null) {
                selected.add(value);
            }
        }
        if (selected.isEmpty()) {
            throw new IllegalArgumentException("No representable rotations for item " + item.id());
        }
        return new BoxItem(new Box(allRotations, selected), item.copies());
    }

    private static List<ItemSpec> itemSpecs(Path path) throws IOException {
        List<ItemSpec> items = new ArrayList<>();
        for (Map<String, String> row : readCsv(path)) {
            items.add(new ItemSpec(
                    row.get("ID"),
                    Integer.parseInt(row.get("X")),
                    Integer.parseInt(row.get("Y")),
                    Integer.parseInt(row.get("Z")),
                    Integer.parseInt(row.get("COPIES")),
                    permittedRotations(row)));
        }
        return items;
    }

    private static Container container(Path bins) throws IOException {
        Map<String, String> row = readCsv(bins).get(0);
        return Container.newBuilder()
                .withId(row.get("ID"))
                .withSize(Integer.parseInt(row.get("X")), Integer.parseInt(row.get("Y")), Integer.parseInt(row.get("Z")))
                .withEmptyWeight(0)
                .withMaxLoadWeight(Integer.MAX_VALUE)
                .build();
    }

    private static Packager<?> packager(String algorithm) {
        return switch (algorithm) {
            case "laff" -> LargestAreaFitFirstPackager.newBuilder().build();
            case "plain" -> PlainPackager.newBuilder().build();
            case "fast_brute_force" -> FastBruteForcePackager.newBuilder().build();
            default -> throw new IllegalArgumentException(algorithm);
        };
    }

    private static Validation validate(
            PackagerResult result,
            List<ItemSpec> itemSpecs,
            Container emptyContainer,
            BufferedWriter certificate,
            String instance,
            String algorithm,
            boolean requireComplete) throws IOException {
        List<String> errors = new ArrayList<>();
        Map<String, ItemSpec> byId = new HashMap<>();
        Map<String, Integer> counts = new HashMap<>();
        for (ItemSpec item : itemSpecs) {
            byId.put(item.id(), item);
        }
        int placements = 0;
        long packedVolume = 0;
        int binIndex = 0;
        for (Container packed : result.getContainers()) {
            List<Placement> list = packed.getStack().getPlacements();
            for (int i = 0; i < list.size(); i++) {
                Placement left = list.get(i);
                String id = left.getBox().getId();
                ItemSpec item = byId.get(id);
                counts.merge(id, 1, Integer::sum);
                placements++;
                packedVolume += left.getVolume();
                if (item == null) {
                    errors.add("unknown item " + id);
                } else if (rotationName(item, left.getStackValue()) == null) {
                    errors.add("forbidden orientation for item " + id);
                }
                if (left.getAbsoluteX() < 0 || left.getAbsoluteY() < 0 || left.getAbsoluteZ() < 0
                        || left.getAbsoluteEndX() >= emptyContainer.getLoadDx()
                        || left.getAbsoluteEndY() >= emptyContainer.getLoadDy()
                        || left.getAbsoluteEndZ() >= emptyContainer.getLoadDz()) {
                    errors.add("out of bounds item " + id + " in bin " + binIndex);
                }
                for (int j = i + 1; j < list.size(); j++) {
                    if (left.intersects3D(list.get(j))) {
                        errors.add("overlap in bin " + binIndex + " between rows " + i + " and " + j);
                    }
                }
                BoxStackValue value = left.getStackValue();
                certificate.write(String.join(",",
                        instance, algorithm, Integer.toString(binIndex), id,
                        Integer.toString(left.getAbsoluteX()), Integer.toString(left.getAbsoluteY()),
                        Integer.toString(left.getAbsoluteZ()), Integer.toString(value.getDx()),
                        Integer.toString(value.getDy()), Integer.toString(value.getDz())));
                certificate.newLine();
            }
            binIndex++;
        }
        int required = 0;
        for (ItemSpec item : itemSpecs) {
            required += item.copies();
            if (requireComplete && counts.getOrDefault(item.id(), 0) != item.copies()) {
                errors.add("item count differs for " + item.id());
            }
        }
        if (requireComplete && placements != required) {
            errors.add("placed " + placements + " of " + required);
        }
        long binVolume = (long) result.size() * emptyContainer.getLoadVolume();
        return new Validation(errors, placements, packedVolume, binVolume);
    }

    private static String jsonEscape(String value) {
        return value.replace("\\", "\\\\").replace("\"", "\\\"");
    }

    private static String jsonArray(List<String> values) {
        StringBuilder out = new StringBuilder("[");
        for (int i = 0; i < values.size(); i++) {
            if (i > 0) out.append(',');
            out.append('"').append(jsonEscape(values.get(i))).append('"');
        }
        return out.append(']').toString();
    }

    private static String sha256(Path path) throws IOException, NoSuchAlgorithmException {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        byte[] hash = digest.digest(Files.readAllBytes(path));
        StringBuilder out = new StringBuilder();
        for (byte value : hash) out.append(String.format("%02x", value));
        return out.toString();
    }

    private static void writeExcluded(BufferedWriter output, Instance instance, String algorithm, String benchmarkId) throws IOException {
        String instanceId = "B07".equals(benchmarkId) ? instance.sourceId() : String.format("THPACK9-%03d", instance.number());
        output.write(String.format(
                "{\"schema_version\":1,\"benchmark_id\":\"%s\",\"instance_id\":\"%s\",\"algorithm\":\"%s\","
                        + "\"status\":\"MALFORMED_SOURCE_EXCLUDED\",\"source_line_valid\":false}",
                benchmarkId, jsonEscape(instanceId), algorithm));
        output.newLine();
    }

    private static void solve(
            BufferedWriter output,
            BufferedWriter certificate,
            Instance instance,
            String algorithm,
            String benchmarkId) throws Exception {
        List<ItemSpec> specs = itemSpecs(instance.items());
        List<BoxItem> items = specs.stream().map(SkjolberThpackCampaign::boxItem).toList();
        int required = specs.stream().mapToInt(ItemSpec::copies).sum();
        Container emptyContainer = container(instance.bins());
        boolean requireComplete = !benchmarkId.equals("B07");
        int availableContainers = requireComplete ? required : 1;
        long started = System.nanoTime();
        PackagerResult result;
        try (Packager<?> selected = packager(algorithm)) {
            PackagerResultBuilder builder = selected.newResultBuilder();
            result = builder
                    .withContainerItems(ContainerItem.newListBuilder().withContainer(emptyContainer, availableContainers).build())
                    .withBoxItems(items)
                    .withMaxContainerCount(availableContainers)
                    .withDeadline(System.currentTimeMillis() + 10_000)
                    .build();
        }
        long wallNanos = System.nanoTime() - started;
        String instanceId = "B07".equals(benchmarkId) ? instance.sourceId() : String.format("THPACK9-%03d", instance.number());
        Validation validation = validate(result, specs, emptyContainer, certificate, instanceId, algorithm, requireComplete);
        boolean success = requireComplete ? result.isSuccess() : !validation.errors().isEmpty() ? false : validation.placements() > 0;
        String status = validation.errors().isEmpty() && success ? "VALID" : "INVALID";
        output.write(String.format(
                "{\"schema_version\":1,\"benchmark_id\":\"%s\",\"instance_id\":\"%s\",\"algorithm\":\"%s\","
                        + "\"status\":\"%s\",\"source_line_valid\":true,\"success\":%s,\"timeout\":%s,"
                        + "\"bins_used\":%d,\"placements\":%d,\"required_items\":%d,"
                        + "\"packed_volume\":%d,\"bin_volume\":%d,\"library_duration_ms\":%d,"
                        + "\"wall_time_ms\":%.6f,\"items_sha256\":\"%s\",\"bins_sha256\":\"%s\","
                        + "\"validation_errors\":%s}",
                benchmarkId, jsonEscape(instanceId), algorithm, status, success, result.isTimeout(), result.size(),
                validation.placements(), required, validation.packedVolume(), validation.binVolume(), result.getDuration(),
                wallNanos / 1_000_000.0, sha256(instance.items()), sha256(instance.bins()),
                jsonArray(validation.errors())));
        output.newLine();
        output.flush();
        certificate.flush();
    }

    private static List<Instance> discover(Path dataRoot) throws IOException {
        List<Instance> result = new ArrayList<>();
        try (var stream = Files.list(dataRoot)) {
            for (Path items : stream.filter(path -> path.getFileName().toString().endsWith("_items.csv")).toList()) {
                String name = items.getFileName().toString();
                String prefix = name.substring(0, name.length() - "_items.csv".length());
                int number = Integer.parseInt(prefix.substring(prefix.lastIndexOf('_') + 1));
                Path bins = dataRoot.resolve(prefix + "_bins.csv");
                if (Files.exists(bins)) result.add(new Instance(prefix, number, items, bins));
            }
        }
        result.sort(Comparator.comparing(Instance::sourceId));
        return result;
    }

    public static void main(String[] args) throws Exception {
        if (args.length < 3 || args.length > 4) {
            throw new IllegalArgumentException("usage: DATA_ROOT OUTPUT_JSONL CERTIFICATE_CSV [BENCHMARK_ID]");
        }
        Path dataRoot = Path.of(args[0]);
        Path outputPath = Path.of(args[1]);
        Path certificatePath = Path.of(args[2]);
        String benchmarkId = args.length == 4 ? args[3] : "B04";
        if (!benchmarkId.equals("B04") && !benchmarkId.equals("B07")) {
            throw new IllegalArgumentException("benchmark id must be B04 or B07");
        }
        Files.createDirectories(outputPath.getParent());
        Files.createDirectories(certificatePath.getParent());
        List<Instance> instances = discover(dataRoot);
        try (BufferedWriter output = Files.newBufferedWriter(outputPath, StandardCharsets.UTF_8);
                BufferedWriter certificate = Files.newBufferedWriter(certificatePath, StandardCharsets.UTF_8)) {
            certificate.write("INSTANCE,ALGORITHM,BIN_INDEX,ITEM_ID,X,Y,Z,DX,DY,DZ");
            certificate.newLine();
            for (Instance instance : instances) {
                for (String algorithm : Arrays.asList("laff", "plain", "fast_brute_force")) {
                    if (benchmarkId.equals("B04") && MALFORMED.contains(instance.number())) {
                        writeExcluded(output, instance, algorithm, benchmarkId);
                    } else {
                        solve(output, certificate, instance, algorithm, benchmarkId);
                    }
                    System.err.printf("%s %s %s%n", benchmarkId, instance.sourceId(), algorithm);
                }
            }
        }
    }
}
