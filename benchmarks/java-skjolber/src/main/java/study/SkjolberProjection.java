package study;

import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import com.github.skjolber.packing.api.Box;
import com.github.skjolber.packing.api.BoxItem;
import com.github.skjolber.packing.api.Container;
import com.github.skjolber.packing.api.ContainerItem;
import com.github.skjolber.packing.api.Packager;
import com.github.skjolber.packing.api.PackagerResult;
import com.github.skjolber.packing.api.Placement;
import com.github.skjolber.packing.packer.bruteforce.FastBruteForcePackager;
import com.github.skjolber.packing.packer.laff.LargestAreaFitFirstPackager;
import com.github.skjolber.packing.packer.plain.PlainPackager;

/**
 * Small, dependency-free CSV sidecar used by protocol-v3 projection tests.
 * The Python harness remains the authoritative validator; this class only
 * translates canonical item/bin rows to the Skjolber API and emits placements.
 */
public final class SkjolberProjection {
    private record Item(String id, int x, int y, int z, int weight) {}
    private record Bin(String id, int x, int y, int z, int maxWeight, int copies) {}

    private static List<Map<String, String>> csv(Path path) throws IOException {
        List<String> lines = Files.readAllLines(path, StandardCharsets.UTF_8);
        if (lines.isEmpty()) throw new IllegalArgumentException("empty CSV: " + path);
        String[] headers = lines.get(0).split(",", -1);
        List<Map<String, String>> rows = new ArrayList<>();
        for (int i = 1; i < lines.size(); i++) {
            if (lines.get(i).isBlank()) continue;
            String[] values = lines.get(i).split(",", -1);
            if (values.length != headers.length) throw new IllegalArgumentException("CSV width mismatch at " + path + ":" + (i + 1));
            Map<String, String> row = new HashMap<>();
            for (int j = 0; j < headers.length; j++) row.put(headers[j], values[j]);
            rows.add(row);
        }
        return rows;
    }

    private static int integer(Map<String, String> row, String key, int fallback) {
        String value = row.get(key);
        return value == null || value.isBlank() ? fallback : Integer.parseInt(value);
    }

    private static List<Item> readItems(Path path) throws IOException {
        List<Item> result = new ArrayList<>();
        for (Map<String, String> row : csv(path)) {
            int copies = integer(row, "COPIES", 1);
            for (int copy = 0; copy < copies; copy++) {
                String id = row.get("ID") + (copies == 1 ? "" : ":" + copy);
                result.add(new Item(id, integer(row, "X", 0), integer(row, "Y", 0), integer(row, "Z", 0), integer(row, "WEIGHT", 1)));
            }
        }
        return result;
    }

    private static List<Bin> readBins(Path path) throws IOException {
        List<Bin> result = new ArrayList<>();
        for (Map<String, String> row : csv(path)) {
            result.add(new Bin(row.get("ID"), integer(row, "X", 0), integer(row, "Y", 0), integer(row, "Z", 0), integer(row, "MAXIMUM_WEIGHT", Integer.MAX_VALUE), integer(row, "COPIES", 1)));
        }
        return result;
    }

    private static BoxItem box(Item item) {
        return new BoxItem(Box.newBuilder().withId(item.id()).withSize(item.x(), item.y(), item.z()).withWeight(item.weight()).withRotate3D().build(), 1);
    }

    private static Packager<?> packager(String algorithm) {
        return switch (algorithm) {
            case "plain" -> PlainPackager.newBuilder().build();
            case "laff" -> LargestAreaFitFirstPackager.newBuilder().build();
            case "fast_brute_force" -> FastBruteForcePackager.newBuilder().build();
            default -> throw new IllegalArgumentException("unknown algorithm: " + algorithm);
        };
    }

    private static String quote(String value) {
        return "\"" + value.replace("\\", "\\\\").replace("\"", "\\\"") + "\"";
    }

    private static String number(double value) {
        if (value == Math.rint(value)) return Long.toString((long) value);
        return Double.toString(value);
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 5) throw new IllegalArgumentException("usage: ITEMS.csv BINS.csv ALGORITHM DEADLINE_MS OUTPUT.json");
        Path itemPath = Path.of(args[0]);
        Path binPath = Path.of(args[1]);
        String algorithm = args[2];
        long deadlineMs = Long.parseLong(args[3]);
        Path outputPath = Path.of(args[4]);
        List<Item> items = readItems(itemPath);
        List<Bin> bins = readBins(binPath);
        List<BoxItem> boxes = items.stream().map(SkjolberProjection::box).toList();
        List<ContainerItem> containers = new ArrayList<>();
        for (Bin bin : bins) {
            Container container = Container.newBuilder().withId(bin.id()).withSize(bin.x(), bin.y(), bin.z()).withEmptyWeight(0).withMaxLoadWeight(bin.maxWeight()).build();
            containers.addAll(ContainerItem.newListBuilder().withContainer(container, bin.copies()).build());
        }
        long started = System.nanoTime();
        PackagerResult result;
        try (Packager<?> selected = packager(algorithm)) {
            result = selected.newResultBuilder().withContainerItems(containers).withBoxItems(boxes)
                    .withMaxContainerCount(Math.max(1, bins.stream().mapToInt(Bin::copies).sum()))
                    .withDeadline(System.currentTimeMillis() + deadlineMs).build();
        }
        long elapsedNs = System.nanoTime() - started;
        try (BufferedWriter writer = Files.newBufferedWriter(outputPath, StandardCharsets.UTF_8)) {
            writer.write("{\"library\":\"skjolber/3d-bin-container-packing\",\"commit\":\"c73d52190c029a14e64f1bbdd2ea70452d1eb83d\",\"algorithm\":");
            writer.write(quote(algorithm));
            writer.write(",\"success\":");
            writer.write(Boolean.toString(result.isSuccess()));
            writer.write(",\"timeout\":");
            writer.write(Boolean.toString(result.isTimeout()));
            writer.write(",\"bins_used\":");
            writer.write(Integer.toString(result.size()));
            writer.write(",\"elapsed_s\":");
            writer.write(number(elapsedNs / 1_000_000_000.0));
            writer.write(",\"placements\":[");
            boolean first = true;
            for (Container packed : result.getContainers()) {
                for (Placement placement : packed.getStack().getPlacements()) {
                    if (!first) writer.write(",");
                    first = false;
                    writer.write("{\"item_id\":");
                    writer.write(quote(placement.getBox().getId()));
                    writer.write(",\"bin_id\":");
                    writer.write(quote(packed.getId()));
                    writer.write(",\"position\":[");
                    writer.write(number(placement.getAbsoluteX())); writer.write(",");
                    writer.write(number(placement.getAbsoluteY())); writer.write(",");
                    writer.write(number(placement.getAbsoluteZ()));
                    writer.write("],\"size\":[");
                    writer.write(number(placement.getStackValue().getDx())); writer.write(",");
                    writer.write(number(placement.getStackValue().getDy())); writer.write(",");
                    writer.write(number(placement.getStackValue().getDz()));
                    writer.write("]}");
                }
            }
            writer.write("]}");
        }
        // Keep stdout machine-readable for the Python protocol harness while
        // retaining the output file as an auditable sidecar artifact.
        System.out.println(Files.readString(outputPath, StandardCharsets.UTF_8));
    }
}
