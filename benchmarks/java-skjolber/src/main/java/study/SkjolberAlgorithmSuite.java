package study;

import java.util.ArrayList;
import java.util.List;

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

public class SkjolberAlgorithmSuite {

    private record Outcome(String algorithm, boolean success, boolean timeout, int bins, int placements,
            long libraryDurationMs, double wallTimeMs, List<String> validationErrors) {}

    private static Box item(String id, int x, int y, int z) {
        return Box.newBuilder().withId(id).withSize(x, y, z).withWeight(1).withRotate3D().build();
    }

    private static Outcome solve(String algorithm, Packager<?> packager, List<BoxItem> items) throws Exception {
        Container container = Container.newBuilder()
                .withId("grid")
                .withSize(10, 10, 10)
                .withEmptyWeight(0)
                .withMaxLoadWeight(100)
                .build();
        long started = System.nanoTime();
        PackagerResult result;
        try (packager) {
            result = packager.newResultBuilder()
                    .withContainerItems(ContainerItem.newListBuilder().withContainer(container, 1).build())
                    .withBoxItems(items)
                    .withMaxContainerCount(1)
                    .withDeadline(System.currentTimeMillis() + 10_000)
                    .build();
        }
        long wall = System.nanoTime() - started;
        List<String> errors = new ArrayList<>();
        int placements = 0;
        for (Container packed : result.getContainers()) {
            List<Placement> list = packed.getStack().getPlacements();
            placements += list.size();
            for (int i = 0; i < list.size(); i++) {
                Placement left = list.get(i);
                if (left.getAbsoluteX() < 0 || left.getAbsoluteY() < 0 || left.getAbsoluteZ() < 0
                        || left.getAbsoluteEndX() >= 10 || left.getAbsoluteEndY() >= 10
                        || left.getAbsoluteEndZ() >= 10) {
                    errors.add("out of bounds placement " + i);
                }
                for (int j = i + 1; j < list.size(); j++) {
                    if (left.intersects3D(list.get(j))) {
                        errors.add("overlap " + i + "/" + j);
                    }
                }
            }
        }
        if (placements != 6) errors.add("placed " + placements + " of 6");
        return new Outcome(algorithm, result.isSuccess(), result.isTimeout(), result.size(), placements,
                result.getDuration(), wall / 1_000_000.0, errors);
    }

    private static String json(Outcome outcome) {
        return String.format(
                "{\"algorithm\":\"%s\",\"success\":%s,\"timeout\":%s,\"bins_used\":%d,"
                        + "\"placements\":%d,\"library_duration_ms\":%d,\"wall_time_ms\":%.6f,"
                        + "\"validation_status\":\"%s\",\"validation_errors\":%s}",
                outcome.algorithm(), outcome.success(), outcome.timeout(), outcome.bins(), outcome.placements(),
                outcome.libraryDurationMs(), outcome.wallTimeMs(),
                outcome.validationErrors().isEmpty() ? "PASS" : "FAIL",
                outcome.validationErrors().isEmpty() ? "[]" : "[\"validation failure\"]");
    }

    public static void main(String[] args) throws Exception {
        List<BoxItem> items = List.of(
                new BoxItem(item("a", 2, 2, 2), 1),
                new BoxItem(item("b", 2, 2, 3), 1),
                new BoxItem(item("c", 2, 3, 2), 1),
                new BoxItem(item("d", 3, 2, 2), 1),
                new BoxItem(item("e", 3, 3, 2), 1),
                new BoxItem(item("f", 2, 3, 3), 1));
        List<Outcome> outcomes = List.of(
                solve("laff", LargestAreaFitFirstPackager.newBuilder().build(), items),
                solve("plain", PlainPackager.newBuilder().build(), items),
                solve("fast_brute_force", FastBruteForcePackager.newBuilder().build(), items));
        System.out.println("{\"schema_version\":1,\"suite\":\"skjolber-algorithm-small/1\","
                + "\"source_commit\":\"c73d52190c029a14e64f1bbdd2ea70452d1eb83d\","
                + "\"scenario\":\"six_distinct_items_one_bin\",\"records\":["
                + json(outcomes.get(0)) + "," + json(outcomes.get(1)) + "," + json(outcomes.get(2)) + "]}");
        if (outcomes.stream().anyMatch(outcome -> !outcome.validationErrors().isEmpty())) {
            System.exit(2);
        }
    }
}
