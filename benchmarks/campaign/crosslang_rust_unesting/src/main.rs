use serde::{Deserialize, Serialize};
use serde_json::json;
use std::collections::{HashMap, HashSet};
use std::env;
use std::time::Instant;
use u_nesting_d3::geometry::OrientationConstraint;
use u_nesting_d3::{Boundary3D, Config, Geometry3D, Packer3D, Solver, Strategy};

const SOURCE_COMMIT: &str = "8cde85b029e4ade663185dacb93fd74440af170d";

#[derive(Clone, Deserialize, Serialize)]
struct BinSpec {
    id: String,
    size: [f64; 3],
    max_weight: f64,
    cost: f64,
}

#[derive(Clone, Deserialize, Serialize)]
struct ItemSpec {
    id: String,
    size: [f64; 3],
    weight: f64,
    orientation_requirement: String,
}

#[derive(Deserialize)]
struct ExternalScenario {
    scenario: String,
    bins: Vec<BinSpec>,
    items: Vec<ItemSpec>,
}

#[derive(Serialize)]
struct Placement {
    item_id: String,
    bin_id: String,
    position: [f64; 3],
    size: [f64; 3],
    original_size: [f64; 3],
    weight: f64,
    rotation: String,
    rotation_index: usize,
}

#[derive(Serialize)]
struct ScenarioOutput {
    campaign_version: &'static str,
    library: &'static str,
    commit: &'static str,
    language: &'static str,
    toolchain: &'static str,
    algorithm: &'static str,
    scenario: String,
    capability_status: String,
    capability_note: String,
    parameters: serde_json::Value,
    bins: Vec<BinSpec>,
    items: Vec<ItemSpec>,
    placements: Vec<Placement>,
    unplaced: Vec<String>,
    elapsed_ms: f64,
}

fn bin(id: impl Into<String>, size: [f64; 3], max_weight: f64, cost: f64) -> BinSpec {
    BinSpec {
        id: id.into(),
        size,
        max_weight,
        cost,
    }
}

fn item(id: impl Into<String>, size: [f64; 3], weight: f64, orientation: &str) -> ItemSpec {
    ItemSpec {
        id: id.into(),
        size,
        weight,
        orientation_requirement: orientation.to_string(),
    }
}

fn repeated_items(prefix: &str, size: [f64; 3], weight: f64, count: usize) -> Vec<ItemSpec> {
    (0..count)
        .map(|i| item(format!("{prefix}-{i:03}"), size, weight, "any"))
        .collect()
}

fn scenario(name: &str) -> (Vec<BinSpec>, Vec<ItemSpec>, &'static str, &'static str) {
    match name {
        "exact_grid" => (
            vec![bin("bin-000", [10.0, 10.0, 10.0], 100.0, 1.0)],
            repeated_items("cube", [5.0, 5.0, 5.0], 1.0, 8),
            "SUPPORTED",
            "single physical boundary",
        ),
        "rotation_required" => (
            vec![bin("bin-000", [4.0, 3.0, 2.0], 100.0, 1.0)],
            vec![item("rotated-000", [3.0, 2.0, 4.0], 1.0, "any")],
            "SUPPORTED",
            "OrientationConstraint::Any must choose a non-identity axis permutation",
        ),
        "rotation_forbidden" => (
            vec![bin("bin-000", [4.0, 3.0, 2.0], 100.0, 1.0)],
            vec![item("upright-000", [3.0, 2.0, 4.0], 1.0, "fixed")],
            "SUPPORTED",
            "OrientationConstraint::Fixed should leave the item unplaced",
        ),
        "weight_limit" => (
            (0..3)
                .map(|i| bin(format!("bin-{i:03}"), [10.0, 10.0, 10.0], 10.0, 1.0))
                .collect(),
            repeated_items("heavy", [4.0, 4.0, 4.0], 6.0, 3),
            "SUPPORTED_VIA_REPEATED_SINGLE_BIN_ADAPTER",
            "Boundary3D::max_mass is native; multiple bins are repeated adapter calls",
        ),
        "heterogeneous_small_first" => (
            vec![
                bin("small-000", [6.0, 5.0, 5.0], 100.0, 7.0),
                bin("small-001", [6.0, 5.0, 5.0], 100.0, 7.0),
                bin("large-000", [12.0, 5.0, 5.0], 100.0, 10.0),
            ],
            repeated_items("heterogeneous", [6.0, 5.0, 5.0], 1.0, 2),
            "NOT_SUPPORTED",
            "Packer3D accepts one Boundary3D and has no heterogeneous-bin cost/copies master",
        ),
        "heterogeneous_large_first" => (
            vec![
                bin("large-000", [12.0, 5.0, 5.0], 100.0, 10.0),
                bin("small-000", [6.0, 5.0, 5.0], 100.0, 7.0),
                bin("small-001", [6.0, 5.0, 5.0], 100.0, 7.0),
            ],
            repeated_items("heterogeneous", [6.0, 5.0, 5.0], 1.0, 2),
            "NOT_SUPPORTED",
            "input order cannot be tested natively because the API has one Boundary3D per solve",
        ),
        "thpack9_instance1" => {
            let bins = (0..80)
                .map(|i| bin(format!("bin-{i:03}"), [10.0, 6.0, 16.0], 100000.0, 1.0))
                .collect();
            let mut items = repeated_items("small", [2.0, 6.0, 8.0], 1.0, 20);
            items.extend(repeated_items("large", [8.0, 4.0, 10.0], 1.0, 50));
            (bins, items, "ADAPTER_REPEATED_SINGLE_BIN", "u-nesting is a single-boundary packer; the campaign repeats it until all items are placed")
        }
        _ => panic!("unknown scenario: {name}"),
    }
}

fn orientation(value: &str) -> OrientationConstraint {
    match value {
        "fixed" => OrientationConstraint::Fixed,
        "upright" => OrientationConstraint::Upright,
        _ => OrientationConstraint::Any,
    }
}

fn orientation_label(requirement: &str, index: usize) -> String {
    let variants: &[(usize, usize, usize)] = match requirement {
        "fixed" => &[(0, 1, 2)],
        "upright" => &[(0, 1, 2), (1, 0, 2)],
        _ => &[
            (0, 1, 2),
            (0, 2, 1),
            (1, 0, 2),
            (1, 2, 0),
            (2, 0, 1),
            (2, 1, 0),
        ],
    };
    let axes = ['x', 'y', 'z'];
    let (a, b, c) = variants.get(index).copied().unwrap_or((0, 1, 2));
    [axes[a], axes[b], axes[c]].iter().collect()
}

fn oriented_size(spec: &ItemSpec, index: usize) -> [f64; 3] {
    let variants: &[(usize, usize, usize)] = match spec.orientation_requirement.as_str() {
        "fixed" => &[(0, 1, 2)],
        "upright" => &[(0, 1, 2), (1, 0, 2)],
        _ => &[
            (0, 1, 2),
            (0, 2, 1),
            (1, 0, 2),
            (1, 2, 0),
            (2, 0, 1),
            (2, 1, 0),
        ],
    };
    let (a, b, c) = variants.get(index).copied().unwrap_or((0, 1, 2));
    [spec.size[a], spec.size[b], spec.size[c]]
}

fn strategy_parameters(
    strategy: Strategy,
    strategy_name: &str,
    time_limit_ms: u64,
) -> serde_json::Value {
    let rayon_threads = env::var("RAYON_NUM_THREADS").ok();
    match strategy {
        Strategy::BottomLeftFill => json!({
            "strategy_requested": strategy_name,
            "decoder": "layer/row",
            "seed_requested": 42,
            "seed_applicable": false,
            "seed_effective": false,
            "time_limit_ms_requested_per_bin": time_limit_ms,
            "time_limit_effective": true,
            "rayon_num_threads_env": rayon_threads,
        }),
        Strategy::GeneticAlgorithm => json!({
            "strategy_requested": strategy_name,
            "decoder": "layer_place_items",
            "population_size_effective": 100,
            "max_generations_effective": 500,
            "crossover_rate_effective": 0.85,
            "mutation_rate_effective": 0.05,
            "seed_requested": 42,
            "seed_applicable": true,
            "seed_effective": false,
            "time_limit_ms_requested_per_bin": time_limit_ms,
            "time_limit_effective": false,
            "rayon_num_threads_env": rayon_threads,
        }),
        Strategy::Brkga => json!({
            "strategy_requested": strategy_name,
            "decoder": "layer_place_items",
            "population_size_effective": 50,
            "max_generations_effective": 100,
            "elite_fraction_effective": 0.2,
            "mutant_fraction_effective": 0.15,
            "elite_bias_effective": 0.7,
            "seed_requested": 42,
            "seed_applicable": true,
            "seed_effective": false,
            "time_limit_ms_requested_per_bin": time_limit_ms,
            "time_limit_effective": false,
            "rayon_num_threads_env": rayon_threads,
        }),
        Strategy::SimulatedAnnealing => json!({
            "strategy_requested": strategy_name,
            "decoder": "layer_place_items",
            "initial_temperature_effective": 100.0,
            "final_temperature_effective": 0.1,
            "cooling_rate_effective": 0.95,
            "iterations_per_temperature_effective": 50,
            "max_iterations_effective": 10000,
            "seed_requested": 42,
            "seed_applicable": true,
            "seed_effective": false,
            "time_limit_ms_requested_per_bin": time_limit_ms,
            "time_limit_effective": false,
            "rayon_num_threads_env": rayon_threads,
        }),
        Strategy::ExtremePoint => json!({
            "strategy_requested": strategy_name,
            "placement_rule": "first feasible orientation at first feasible extreme point",
            "seed_requested": 42,
            "seed_applicable": false,
            "seed_effective": false,
            "time_limit_ms_requested_per_bin": time_limit_ms,
            "time_limit_effective": false,
            "rayon_num_threads_env": rayon_threads,
        }),
        _ => json!({
            "strategy_requested": strategy_name,
            "seed_requested": 42,
            "seed_effective": false,
            "time_limit_ms_requested_per_bin": time_limit_ms,
            "time_limit_effective": false,
            "rayon_num_threads_env": rayon_threads,
        }),
    }
}

fn solve_one_bin(
    bin_spec: &BinSpec,
    items: &[ItemSpec],
    strategy: Strategy,
    time_limit_ms: u64,
) -> (Vec<Placement>, Vec<String>) {
    let geometries: Vec<Geometry3D> = items
        .iter()
        .map(|i| {
            Geometry3D::new(i.id.clone(), i.size[0], i.size[1], i.size[2])
                .with_mass(i.weight)
                .with_orientation(orientation(&i.orientation_requirement))
        })
        .collect();
    let boundary = Boundary3D::new(bin_spec.size[0], bin_spec.size[1], bin_spec.size[2])
        .with_max_mass(bin_spec.max_weight);
    let config = Config::default()
        .with_strategy(strategy)
        .with_time_limit(time_limit_ms)
        .with_seed(42);
    let result = Packer3D::new(config)
        .solve(&geometries, &boundary)
        .expect("u-nesting solve failed");
    let specs: HashMap<&str, &ItemSpec> = items.iter().map(|i| (i.id.as_str(), i)).collect();
    let placements = result
        .placements
        .iter()
        .map(|p| {
            let spec = specs[p.geometry_id.as_str()];
            let rotation_index = p.rotation_index.unwrap_or(0);
            Placement {
                item_id: p.geometry_id.clone(),
                bin_id: bin_spec.id.clone(),
                position: [p.position[0], p.position[1], p.position[2]],
                size: oriented_size(spec, rotation_index),
                original_size: spec.size,
                weight: spec.weight,
                rotation: orientation_label(&spec.orientation_requirement, rotation_index),
                rotation_index,
            }
        })
        .collect();
    let placed: HashSet<&str> = result
        .placements
        .iter()
        .map(|p| p.geometry_id.as_str())
        .collect();
    let unplaced = items
        .iter()
        .filter(|i| !placed.contains(i.id.as_str()))
        .map(|i| i.id.clone())
        .collect();
    (placements, unplaced)
}

fn main() {
    let arguments: Vec<String> = env::args().collect();
    let first = arguments.get(1).cloned().unwrap_or_else(|| {
        eprintln!("usage: crosslang-rust-unesting <scenario> [strategy] [time-limit-ms] | --input <json> [strategy] [time-limit-ms]");
        std::process::exit(2)
    });
    let (name, bins, items, capability, note, strategy_arg_index) = if first == "--input" {
        let path = arguments.get(2).unwrap_or_else(|| {
            eprintln!("--input requires a JSON path");
            std::process::exit(2)
        });
        let data = std::fs::read_to_string(path).expect("failed to read external scenario");
        let input: ExternalScenario =
            serde_json::from_str(&data).expect("failed to parse external scenario");
        (
            input.scenario,
            input.bins,
            input.items,
            "ADAPTER_MULTI_BIN",
            "u-nesting accepts one Boundary3D; full THPACK9 is repeated single-boundary adapter calls",
            3,
        )
    } else {
        let (bins, items, capability, note) = scenario(&first);
        (first, bins, items, capability, note, 2)
    };
    let strategy_name = arguments
        .get(strategy_arg_index)
        .map(String::as_str)
        .unwrap_or("extremepoint");
    let strategy = Strategy::parse(strategy_name).unwrap_or_else(|| {
        eprintln!("unknown strategy: {strategy_name}");
        std::process::exit(2)
    });
    let time_limit_ms = arguments
        .get(strategy_arg_index + 1)
        .map(|value| value.parse::<u64>().expect("invalid time limit"))
        .unwrap_or(10_000);
    let started = Instant::now();
    let mut placements = Vec::new();
    let mut remaining = items.clone();

    if capability != "NOT_SUPPORTED" {
        for bin_spec in &bins {
            if remaining.is_empty() {
                break;
            }
            let (mut placed, _) = solve_one_bin(bin_spec, &remaining, strategy, time_limit_ms);
            if placed.is_empty() {
                break;
            }
            let placed_ids: HashSet<String> = placed.iter().map(|p| p.item_id.clone()).collect();
            remaining.retain(|i| !placed_ids.contains(&i.id));
            placements.append(&mut placed);
        }
    }

    let out = ScenarioOutput {
        campaign_version: "crosslang-1",
        library: "iyulab/u-nesting",
        commit: SOURCE_COMMIT,
        language: "Rust",
        toolchain: option_env!("CROSSLANG_RUSTC_VERSION").unwrap_or("rustc version not embedded"),
        algorithm: match strategy {
            Strategy::BottomLeftFill => "BottomLeftFill (Layer); repeated single-boundary adapter",
            Strategy::GeneticAlgorithm => "GeneticAlgorithm; repeated single-boundary adapter",
            Strategy::Brkga => "BRKGA; repeated single-boundary adapter",
            Strategy::SimulatedAnnealing => "SimulatedAnnealing; repeated single-boundary adapter",
            Strategy::ExtremePoint => "ExtremePoint; repeated single-boundary adapter",
            _ => "other strategy; repeated single-boundary adapter",
        },
        scenario: name,
        capability_status: capability.to_string(),
        capability_note: note.to_string(),
        parameters: strategy_parameters(strategy, strategy_name, time_limit_ms),
        bins,
        items,
        placements,
        unplaced: remaining.into_iter().map(|i| i.id).collect(),
        elapsed_ms: started.elapsed().as_secs_f64() * 1000.0,
    };
    println!("{}", serde_json::to_string_pretty(&out).unwrap());
}
