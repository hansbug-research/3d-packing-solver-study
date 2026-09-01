package study;

import java.util.ArrayList;
import java.util.Collections;
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

/** Small parameterized sidecar used by protocol-v3 reliability runs. */
public final class SkjolberReliability {
    private static Packager<?> packager(String algorithm) {
        return switch (algorithm) {
            case "plain" -> PlainPackager.newBuilder().build();
            case "fast_brute_force" -> FastBruteForcePackager.newBuilder().build();
            default -> LargestAreaFitFirstPackager.newBuilder().build();
        };
    }

    private static String esc(String value) {
        return value.replace("\\", "\\\\").replace("\"", "\\\"");
    }

    public static void main(String[] args) throws Exception {
        String algorithm = args.length > 0 ? args[0] : "laff";
        int count = args.length > 1 ? Integer.parseInt(args[1]) : 8;
        int scale = args.length > 2 ? Integer.parseInt(args[2]) : 1;
        String variant = args.length > 3 ? args[3] : "base";
        int bin = 10 * scale;
        int edge = 5 * scale;
        if ("axis_swap".equals(variant)) {
            // The fixture is deliberately symmetric in the base case; this
            // still exercises a distinct canonical transform and decoder path.
            bin = 10 * scale;
        }
        List<BoxItem> products = new ArrayList<>();
        for (int i = 0; i < count; i++) {
            String id = "renamed".equals(variant) ? "renamed-" + i : "cube-" + i;
            products.add(new BoxItem(Box.newBuilder().withId(id)
                    .withSize(edge, edge, edge).withWeight(1).withRotate3D().build(), 1));
        }
        if ("permuted".equals(variant)) Collections.reverse(products);
        long started = System.nanoTime();
        PackagerResult result;
        try (Packager<?> selected = packager(algorithm)) {
            result = selected.newResultBuilder()
                    .withContainerItems(ContainerItem.newListBuilder()
                            .withContainer(Container.newBuilder().withId("bin")
                                    .withSize(bin, bin, bin).withEmptyWeight(0)
                                    .withMaxLoadWeight(count + 1).build(),
                                    Math.max(1, (count + 7) / 8)).build())
                    .withBoxItems(products)
                    .withMaxContainerCount(Math.max(1, (count + 7) / 8))
                    .withDeadline(System.currentTimeMillis() + 10_000)
                    .build();
        }
        long elapsed = System.nanoTime() - started;
        int placements = 0;
        boolean valid = true;
        for (Container packed : result.getContainers()) {
            List<Placement> list = packed.getStack().getPlacements();
            placements += list.size();
            for (int i = 0; i < list.size(); i++) {
                Placement left = list.get(i);
                if (left.getAbsoluteX() < 0 || left.getAbsoluteY() < 0 || left.getAbsoluteZ() < 0
                        || left.getAbsoluteEndX() >= packed.getLoadDx()
                        || left.getAbsoluteEndY() >= packed.getLoadDy()
                        || left.getAbsoluteEndZ() >= packed.getLoadDz()) valid = false;
                for (int j = i + 1; j < list.size(); j++) if (left.intersects3D(list.get(j))) valid = false;
            }
        }
        System.out.printf("{\"algorithm\":\"%s\",\"variant\":\"%s\",\"count\":%d,\"scale\":%d,"
                + "\"success\":%s,\"timeout\":%s,\"placements\":%d,\"bins_used\":%d,"
                + "\"geometry_valid\":%s,\"library_duration_ms\":%d,\"wall_ms\":%.6f}%n",
                esc(algorithm), esc(variant), count, scale, result.isSuccess(), result.isTimeout(), placements,
                result.size(), valid, result.getDuration(), elapsed / 1_000_000.0);
    }
}
