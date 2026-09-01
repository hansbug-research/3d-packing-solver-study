package study;

import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
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
import com.github.skjolber.packing.api.Placement;
import com.github.skjolber.packing.packer.bruteforce.FastBruteForcePackager;
import com.github.skjolber.packing.packer.laff.LargestAreaFitFirstPackager;
import com.github.skjolber.packing.packer.plain.PlainPackager;

/** Fixed-pose, complete-load runner for the supplemental MPV corpus. */
public class SkjolberMpvCampaign {
    private record Item(String id, int x, int y, int z) {}
    private record Case(String id, Path items, Path bins) {}

    private static List<Map<String, String>> csv(Path path) throws IOException {
        List<String> lines = Files.readAllLines(path, StandardCharsets.UTF_8);
        List<Map<String, String>> rows = new ArrayList<>();
        String[] keys = lines.get(0).split(",", -1);
        for (int i = 1; i < lines.size(); i++) {
            if (lines.get(i).isBlank()) continue;
            String[] values = lines.get(i).split(",", -1);
            Map<String, String> row = new HashMap<>();
            for (int j = 0; j < keys.length; j++) row.put(keys[j], values[j]);
            rows.add(row);
        }
        return rows;
    }

    private static List<Item> items(Path path) throws IOException {
        List<Item> result = new ArrayList<>();
        for (Map<String, String> row : csv(path)) result.add(new Item(row.get("ID"), Integer.parseInt(row.get("X")), Integer.parseInt(row.get("Y")), Integer.parseInt(row.get("Z"))));
        return result;
    }

    private static Container container(Path path) throws IOException {
        Map<String, String> row = csv(path).get(0);
        return Container.newBuilder().withId(row.get("ID"))
                .withSize(Integer.parseInt(row.get("X")), Integer.parseInt(row.get("Y")), Integer.parseInt(row.get("Z")))
                .withEmptyWeight(0).withMaxLoadWeight(Integer.MAX_VALUE).build();
    }

    private static BoxItem boxItem(Item item) {
        Box all = Box.newBuilder().withId(item.id()).withSize(item.x(), item.y(), item.z()).withWeight(1).withRotate3D().build();
        List<BoxStackValue> selected = new ArrayList<>();
        for (BoxStackValue value : all.getStackValues()) {
            if (value.getDx() == item.x() && value.getDy() == item.y() && value.getDz() == item.z()) selected.add(value);
        }
        if (selected.isEmpty()) throw new IllegalArgumentException("no XYZ pose for " + item.id());
        return new BoxItem(new Box(all, selected), 1);
    }

    private static Packager<?> packager(String algorithm) {
        return switch (algorithm) {
            case "plain" -> PlainPackager.newBuilder().build();
            case "laff" -> LargestAreaFitFirstPackager.newBuilder().build();
            case "fast_brute_force" -> FastBruteForcePackager.newBuilder().build();
            default -> throw new IllegalArgumentException(algorithm);
        };
    }

    private static String esc(String value) { return value.replace("\\", "\\\\").replace("\"", "\\\""); }

    private static String sha256(Path path) throws Exception {
        byte[] digest = MessageDigest.getInstance("SHA-256").digest(Files.readAllBytes(path));
        StringBuilder result = new StringBuilder();
        for (byte value : digest) result.append(String.format("%02x", value));
        return result.toString();
    }

    private static void solve(BufferedWriter out, BufferedWriter certificate, Case test, String algorithm, long budgetMs) throws Exception {
        List<Item> specs = items(test.items());
        Container empty = container(test.bins());
        List<BoxItem> boxes = specs.stream().map(SkjolberMpvCampaign::boxItem).toList();
        long started = System.nanoTime();
        PackagerResult result;
        try (Packager<?> selected = packager(algorithm)) {
            result = selected.newResultBuilder()
                    .withContainerItems(ContainerItem.newListBuilder().withContainer(empty, specs.size()).build())
                    .withBoxItems(boxes).withMaxContainerCount(specs.size())
                    .withDeadline(System.currentTimeMillis() + budgetMs).build();
        }
        long wallNs = System.nanoTime() - started;
        Set<String> expected = new HashSet<>();
        for (Item item : specs) expected.add(item.id());
        Set<String> seen = new HashSet<>();
        List<String> errors = new ArrayList<>();
        long packedVolume = 0;
        int placements = 0;
        for (Container packed : result.getContainers()) {
            List<Placement> values = packed.getStack().getPlacements();
            for (int i = 0; i < values.size(); i++) {
                Placement left = values.get(i);
                String id = left.getBox().getId();
                placements++;
                if (!expected.contains(id) || !seen.add(id)) errors.add("duplicate_or_unknown:" + id);
                if (left.getAbsoluteX() < 0 || left.getAbsoluteY() < 0 || left.getAbsoluteZ() < 0
                        || left.getAbsoluteEndX() >= empty.getLoadDx() || left.getAbsoluteEndY() >= empty.getLoadDy() || left.getAbsoluteEndZ() >= empty.getLoadDz()) errors.add("out_of_bounds:" + id);
                for (int j = i + 1; j < values.size(); j++) if (left.intersects3D(values.get(j))) errors.add("overlap:" + id);
                BoxStackValue pose = left.getStackValue();
                Item spec = specs.stream().filter(candidate -> candidate.id().equals(id)).findFirst().orElse(null);
                if (spec == null || pose.getDx() != spec.x() || pose.getDy() != spec.y() || pose.getDz() != spec.z()) errors.add("forbidden_orientation:" + id);
                packedVolume += left.getVolume();
                certificate.write(String.join(",", test.id(), algorithm, Integer.toString(result.getContainers().indexOf(packed)), id,
                        Integer.toString(left.getAbsoluteX()), Integer.toString(left.getAbsoluteY()), Integer.toString(left.getAbsoluteZ()),
                        Integer.toString(pose.getDx()), Integer.toString(pose.getDy()), Integer.toString(pose.getDz())));
                certificate.newLine();
            }
        }
        boolean complete = seen.size() == expected.size();
        if (!complete) errors.add("incomplete:" + seen.size() + "/" + expected.size());
        String status = errors.isEmpty() && complete ? "VALID_COMPLETE" : errors.isEmpty() ? "VALID_PARTIAL" : "INVALID_CERTIFICATE";
        String runStatus = result.isTimeout() ? "TIME_LIMIT" : "COMPLETED";
        String termination = result.isTimeout() ? "TIME_LIMIT_WITH_INCUMBENT" : "RETURNED_CERTIFICATE";
        StringBuilder errorJson = new StringBuilder("[");
        for (int i = 0; i < errors.size(); i++) {
            if (i > 0) errorJson.append(',');
            errorJson.append('"').append(esc(errors.get(i))).append('"');
        }
        errorJson.append(']');
        out.write(String.format("{\"schema_version\":1,\"protocol_version\":\"benchmark-protocol/3-supplemental\",\"record_kind\":\"SUPPLEMENTAL_ADAPTER_RUN\",\"benchmark_id\":\"B05-MPV-OFFICIAL-GEN\",\"instance_id\":\"%s\",\"implementation_id\":\"skjolber_%s\",\"implementation_version\":\"c73d52190c029a14e64f1bbdd2ea70452d1eb83d\",\"algorithm\":\"%s\",\"comparison_track\":\"NATIVE\",\"problem_scope\":\"FULL_PROBLEM\",\"problem_variant\":\"FIXED_XYZ\",\"solution_status\":\"%s\",\"run_status\":\"%s\",\"termination_reason\":\"%s\",\"timeout\":%s,\"bins_used\":%d,\"packed_items\":%d,\"required_items\":%d,\"packed_volume\":%d,\"library_duration_ms\":%d,\"wall_time_ms\":%.3f,\"items_sha256\":\"%s\",\"bins_sha256\":\"%s\",\"validation_errors\":%s}%n", esc(test.id()), algorithm, algorithm, status, runStatus, termination, result.isTimeout(), result.size(), placements, expected.size(), packedVolume, result.getDuration(), wallNs / 1_000_000.0, sha256(test.items()), sha256(test.bins()), errorJson));
        out.flush();
    }

    private static List<Case> discover(Path root) throws IOException {
        List<Case> result = new ArrayList<>();
        try (var stream = Files.list(root)) {
            for (Path items : stream.filter(path -> path.getFileName().toString().endsWith("_items.csv")).toList()) {
                String name = items.getFileName().toString();
                String id = name.substring(0, name.length() - "_items.csv".length());
                Path bins = root.resolve(id + "_bins.csv");
                if (Files.exists(bins)) result.add(new Case(id, items, bins));
            }
        }
        result.sort(Comparator.comparing(Case::id));
        return result;
    }

    public static void main(String[] args) throws Exception {
        if (args.length < 4 || args.length > 5) throw new IllegalArgumentException("usage: DATA_ROOT OUTPUT_JSONL CERTIFICATE_CSV BUDGET_SECONDS [ALGORITHM]");
        Path root = Path.of(args[0]);
        Path output = Path.of(args[1]);
        Path certificatePath = Path.of(args[2]);
        long budgetMs = Math.round(Double.parseDouble(args[3]) * 1000.0);
        List<String> algorithms = args.length == 5 ? List.of(args[4]) : Arrays.asList("plain", "laff", "fast_brute_force");
        Files.createDirectories(output.toAbsolutePath().getParent());
        Files.createDirectories(certificatePath.toAbsolutePath().getParent());
        try (BufferedWriter out = Files.newBufferedWriter(output, StandardCharsets.UTF_8);
                BufferedWriter certificate = Files.newBufferedWriter(certificatePath, StandardCharsets.UTF_8)) {
            certificate.write("INSTANCE,ALGORITHM,BIN_INDEX,ITEM_ID,X,Y,Z,DX,DY,DZ");
            certificate.newLine();
            for (Case test : discover(root)) for (String algorithm : algorithms) {
                solve(out, certificate, test, algorithm, budgetMs);
                System.err.printf("%s %s%n", test.id(), algorithm);
            }
        }
    }
}
