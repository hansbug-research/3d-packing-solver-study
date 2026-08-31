package study;

import java.util.ArrayList;
import java.util.List;

import com.github.skjolber.packing.api.Box;
import com.github.skjolber.packing.api.BoxItem;
import com.github.skjolber.packing.api.Container;
import com.github.skjolber.packing.api.ContainerItem;
import com.github.skjolber.packing.api.PackagerResult;
import com.github.skjolber.packing.api.Placement;
import com.github.skjolber.packing.packer.laff.LargestAreaFitFirstPackager;

public class SkjolberBenchmark {

    private record Outcome(boolean success, int containers, int placements, long libraryDurationMs,
            long measuredNs, boolean geometryValid) {}

    private static Container container(String id, int x, int y, int z, int maxWeight) {
        return Container.newBuilder()
                .withId(id)
                .withSize(x, y, z)
                .withEmptyWeight(0)
                .withMaxLoadWeight(maxWeight)
                .build();
    }

    private static Box box(String id, int x, int y, int z, int weight, boolean rotate3d, boolean rotate2d) {
        Box.Builder builder = Box.newBuilder().withId(id).withSize(x, y, z).withWeight(weight);
        if (rotate3d) {
            builder.withRotate3D();
        } else if (rotate2d) {
            builder.withRotate2D();
        }
        return builder.build();
    }

    private static Outcome solve(List<ContainerItem> containers, List<BoxItem> products, int maxContainers) {
        try (LargestAreaFitFirstPackager packager = LargestAreaFitFirstPackager.newBuilder().build()) {
            long start = System.nanoTime();
            PackagerResult result = packager.newResultBuilder()
                    .withContainerItems(containers)
                    .withBoxItems(products)
                    .withMaxContainerCount(maxContainers)
                    .withDeadline(System.currentTimeMillis() + 10_000)
                    .build();
            long elapsed = System.nanoTime() - start;
            int placementCount = 0;
            boolean valid = true;
            for (Container packed : result.getContainers()) {
                List<Placement> placements = packed.getStack().getPlacements();
                placementCount += placements.size();
                for (int i = 0; i < placements.size(); i++) {
                    Placement left = placements.get(i);
                    if (left.getAbsoluteX() < 0 || left.getAbsoluteY() < 0 || left.getAbsoluteZ() < 0
                            || left.getAbsoluteEndX() >= packed.getLoadDx()
                            || left.getAbsoluteEndY() >= packed.getLoadDy()
                            || left.getAbsoluteEndZ() >= packed.getLoadDz()) {
                        valid = false;
                    }
                    for (int j = i + 1; j < placements.size(); j++) {
                        if (left.intersects3D(placements.get(j))) {
                            valid = false;
                        }
                    }
                }
            }
            return new Outcome(result.isSuccess(), result.size(), placementCount,
                    result.getDuration(), elapsed, valid);
        }
    }

    private static String json(String name, Outcome outcome) {
        return String.format("\"%s\":{\"success\":%s,\"containers\":%d,\"placements\":%d,"
                        + "\"library_duration_ms\":%d,\"measured_ms\":%.6f,\"geometry_valid\":%s}",
                name, outcome.success, outcome.containers, outcome.placements,
                outcome.libraryDurationMs, outcome.measuredNs / 1_000_000.0, outcome.geometryValid);
    }

    public static void main(String[] args) {
        List<BoxItem> cubes = List.of(new BoxItem(box("cube", 5, 5, 5, 1, true, false), 8));
        Outcome grid = solve(
                ContainerItem.newListBuilder().withContainer(container("grid", 10, 10, 10, 100), 1).build(),
                cubes, 1);

        List<BoxItem> rotationItem3d = List.of(new BoxItem(box("rotated", 3, 2, 4, 1, true, false), 1));
        Outcome rotationAllowed = solve(
                ContainerItem.newListBuilder().withContainer(container("rotation", 4, 3, 2, 100), 1).build(),
                rotationItem3d, 1);

        List<BoxItem> rotationItem2d = List.of(new BoxItem(box("upright", 3, 2, 4, 1, false, true), 1));
        Outcome rotationForbidden = solve(
                ContainerItem.newListBuilder().withContainer(container("rotation", 4, 3, 2, 100), 1).build(),
                rotationItem2d, 1);

        List<BoxItem> heavy = List.of(new BoxItem(box("heavy", 4, 4, 4, 6, true, false), 3));
        Outcome weight = solve(
                ContainerItem.newListBuilder().withContainer(container("weight", 10, 10, 10, 10), 3).build(),
                heavy, 3);

        List<BoxItem> medium = new ArrayList<>();
        for (int i = 0; i < 100; i++) {
            medium.add(new BoxItem(box("m" + i, 5 + i % 4, 4 + i % 3, 3 + i % 5, 1, true, false), 1));
        }
        Outcome hundred = solve(
                ContainerItem.newListBuilder().withContainer(container("medium", 50, 50, 50, 1000), 4).build(),
                medium, 4);

        // Public THPACK9 instance 1 (ESICUP): 20 boxes of 2x6x8 and 50 boxes
        // of 8x4x10 in 10x6x16 containers. The source has no weights/prices.
        List<BoxItem> thpack9 = new ArrayList<>();
        for (int i = 0; i < 20; i++)
            thpack9.add(new BoxItem(box("th-small-" + i, 2, 6, 8, 1, true, false), 1));
        for (int i = 0; i < 50; i++)
            thpack9.add(new BoxItem(box("th-large-" + i, 8, 4, 10, 1, true, false), 1));
        Outcome thpack9Outcome = solve(
                ContainerItem.newListBuilder().withContainer(container("thpack9", 10, 6, 16, 100000), 80).build(),
                thpack9, 80);

        System.out.println("{\"library\":\"skjolber/3d-bin-container-packing\","
                + "\"commit\":\"c73d52190c029a14e64f1bbdd2ea70452d1eb83d\",\"algorithm\":\"LAFF\",\"scenarios\":{"
                + json("exact_grid", grid) + ","
                + json("rotation_allowed_3d", rotationAllowed) + ","
                + json("rotation_forbidden_upright", rotationForbidden) + ","
                + json("weight_limit", weight) + ","
                + json("hundred_items", hundred) + ","
                + json("thpack9_instance1", thpack9Outcome)
                + "}}" );
    }
}
