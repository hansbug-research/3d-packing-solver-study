package main

import (
	"encoding/json"
	"fmt"
	"os"
	"runtime"
	"sort"
	"time"

	"github.com/gedex/bp3d"
)

const sourceCommit = "0ba3dcda7ab334c19b0979b1cf1fa05e09f33bc7"

type binSpec struct {
	ID        string     `json:"id"`
	Size      [3]float64 `json:"size"`
	MaxWeight float64    `json:"max_weight"`
	Cost      float64    `json:"cost"`
}

type itemSpec struct {
	ID          string     `json:"id"`
	Size        [3]float64 `json:"size"`
	Weight      float64    `json:"weight"`
	Orientation string     `json:"orientation_requirement"`
}

type placement struct {
	ItemID      string     `json:"item_id"`
	BinID       string     `json:"bin_id"`
	Position    [3]float64 `json:"position"`
	Size        [3]float64 `json:"size"`
	Original    [3]float64 `json:"original_size"`
	Weight      float64    `json:"weight"`
	Rotation    string     `json:"rotation"`
	RotationIdx int        `json:"rotation_index"`
}

type scenarioOutput struct {
	CampaignVersion string                 `json:"campaign_version"`
	Library         string                 `json:"library"`
	Commit          string                 `json:"commit"`
	Language        string                 `json:"language"`
	Toolchain       string                 `json:"toolchain"`
	Algorithm       string                 `json:"algorithm"`
	Scenario        string                 `json:"scenario"`
	Capability      string                 `json:"capability_status"`
	CapabilityNote  string                 `json:"capability_note"`
	Parameters      map[string]interface{} `json:"parameters"`
	Bins            []binSpec              `json:"bins"`
	Items           []itemSpec             `json:"items"`
	Placements      []placement            `json:"placements"`
	Unplaced        []string               `json:"unplaced"`
	ElapsedMS       float64                `json:"elapsed_ms"`
}

type externalScenario struct {
	Scenario string     `json:"scenario"`
	Bins     []binSpec  `json:"bins"`
	Items    []itemSpec `json:"items"`
}

func item(id string, size [3]float64, weight float64, orientation string) itemSpec {
	return itemSpec{ID: id, Size: size, Weight: weight, Orientation: orientation}
}

func repeatedItems(prefix string, size [3]float64, weight float64, count int) []itemSpec {
	items := make([]itemSpec, 0, count)
	for i := 0; i < count; i++ {
		items = append(items, item(fmt.Sprintf("%s-%03d", prefix, i), size, weight, "any"))
	}
	return items
}

func scenario(name string) ([]binSpec, []itemSpec, string, string) {
	switch name {
	case "exact_grid":
		return []binSpec{{"bin-000", [3]float64{10, 10, 10}, 100, 1}}, repeatedItems("cube", [3]float64{5, 5, 5}, 1, 8), "SUPPORTED", "single physical bin"
	case "rotation_required":
		return []binSpec{{"bin-000", [3]float64{4, 3, 2}, 100, 1}}, []itemSpec{item("rotated-000", [3]float64{3, 2, 4}, 1, "any")}, "SUPPORTED", "requires a non-identity axis permutation"
	case "rotation_forbidden":
		return []binSpec{{"bin-000", [3]float64{4, 3, 2}, 100, 1}}, []itemSpec{item("upright-000", [3]float64{3, 2, 4}, 1, "fixed")}, "NOT_SUPPORTED", "bp3d exposes no per-item orientation whitelist; the observed run remains unrestricted"
	case "weight_limit":
		bins := []binSpec{}
		for i := 0; i < 3; i++ {
			bins = append(bins, binSpec{fmt.Sprintf("bin-%03d", i), [3]float64{10, 10, 10}, 10, 1})
		}
		return bins, repeatedItems("heavy", [3]float64{4, 4, 4}, 6, 3), "DOCUMENTED_FIELD_NOT_ENFORCED", "MaxWeight exists but PutItem never checks accumulated weight"
	case "heterogeneous_small_first":
		return []binSpec{{"small-000", [3]float64{6, 5, 5}, 100, 7}, {"small-001", [3]float64{6, 5, 5}, 100, 7}, {"large-000", [3]float64{12, 5, 5}, 100, 10}}, repeatedItems("heterogeneous", [3]float64{6, 5, 5}, 1, 2), "NO_COST_OBJECTIVE", "input order is small then large; bp3d sorts bins by volume"
	case "heterogeneous_large_first":
		return []binSpec{{"large-000", [3]float64{12, 5, 5}, 100, 10}, {"small-000", [3]float64{6, 5, 5}, 100, 7}, {"small-001", [3]float64{6, 5, 5}, 100, 7}}, repeatedItems("heterogeneous", [3]float64{6, 5, 5}, 1, 2), "NO_COST_OBJECTIVE", "input order is large then small; bp3d sorts bins by volume"
	case "thpack9_instance1":
		bins := make([]binSpec, 0, 80)
		for i := 0; i < 80; i++ {
			bins = append(bins, binSpec{fmt.Sprintf("bin-%03d", i), [3]float64{10, 6, 16}, 100000, 1})
		}
		items := repeatedItems("small", [3]float64{2, 6, 8}, 1, 20)
		items = append(items, repeatedItems("large", [3]float64{8, 4, 10}, 1, 50)...)
		return bins, items, "SUPPORTED", "ESICUP THPACK9 instance 1, 80 physical bins"
	default:
		panic("unknown scenario: " + name)
	}
}

func main() {
	if len(os.Args) < 2 {
		fmt.Fprintln(os.Stderr, "usage: crosslang_go_bp3d <scenario> | --input <json>")
		os.Exit(2)
	}
	var name, capability, note string
	var bins []binSpec
	var items []itemSpec
	if os.Args[1] == "--input" {
		if len(os.Args) != 3 {
			fmt.Fprintln(os.Stderr, "usage: crosslang_go_bp3d --input <json>")
			os.Exit(2)
		}
		data, err := os.ReadFile(os.Args[2])
		if err != nil {
			panic(err)
		}
		var input externalScenario
		if err := json.Unmarshal(data, &input); err != nil {
			panic(err)
		}
		name, bins, items = input.Scenario, input.Bins, input.Items
		capability = "SUPPORTED_NATIVE_MULTI_BIN"
		note = "THPACK9 multi-container BPP expressed with one physical Bin object per candidate container"
	} else {
		bins, items, capability, note = scenario(os.Args[1])
		name = os.Args[1]
	}
	packer := bp3d.NewPacker()
	for _, b := range bins {
		packer.AddBin(bp3d.NewBin(b.ID, b.Size[0], b.Size[1], b.Size[2], b.MaxWeight))
	}
	for _, i := range items {
		packer.AddItem(bp3d.NewItem(i.ID, i.Size[0], i.Size[1], i.Size[2], i.Weight))
	}
	started := time.Now()
	err := packer.Pack()
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	elapsed := float64(time.Since(started).Nanoseconds()) / 1e6
	original := map[string]itemSpec{}
	for _, i := range items {
		original[i.ID] = i
	}
	placements := []placement{}
	for _, b := range packer.Bins {
		for _, i := range b.Items {
			d := i.GetDimension()
			s := original[i.Name]
			placements = append(placements, placement{
				ItemID: i.Name, BinID: b.Name,
				Position: [3]float64{i.Position[0], i.Position[1], i.Position[2]},
				Size:     [3]float64{d[0], d[1], d[2]}, Original: s.Size, Weight: i.Weight,
				Rotation: i.RotationType.String(), RotationIdx: int(i.RotationType),
			})
		}
	}
	sort.Slice(placements, func(i, j int) bool {
		if placements[i].BinID == placements[j].BinID {
			return placements[i].ItemID < placements[j].ItemID
		}
		return placements[i].BinID < placements[j].BinID
	})
	unplaced := []string{}
	for _, i := range packer.UnfitItems {
		unplaced = append(unplaced, i.Name)
	}
	for _, i := range packer.Items {
		unplaced = append(unplaced, i.Name)
	}
	out := scenarioOutput{
		CampaignVersion: "crosslang-1", Library: "gedex/bp3d", Commit: sourceCommit,
		Language: "Go", Toolchain: runtime.Version(), Algorithm: "pivot greedy",
		Scenario: name, Capability: capability, CapabilityNote: note,
		Parameters: map[string]interface{}{"physical_bin_objects": len(bins), "library_sort": "ascending bin volume / descending item volume"},
		Bins:       bins, Items: items, Placements: placements, Unplaced: unplaced, ElapsedMS: elapsed,
	}
	encoder := json.NewEncoder(os.Stdout)
	encoder.SetIndent("", "  ")
	if err := encoder.Encode(out); err != nil {
		panic(err)
	}
}
