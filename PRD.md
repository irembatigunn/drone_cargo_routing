# Drone Cargo Routing Optimization System — PRD

**Version:** 1.0
**Document Type:** Product Requirements & Technical Specification

---

## 1. Sistem Genel Bakışı

Sistem, çoklu drone filosuyla zaman pencereli (time-windowed), kapasite kısıtlı, no-fly zone içeren bir 2D operasyon alanında **multi-trip cargo delivery routing** problemini optimize eden bir AI uygulamasıdır. Tek depo merkezli, homojen drone fleet'iyle çalışır. Sistem üç temel AI pilarını entegre eder:

- **Logic Layer**: Forward-chaining inference engine, First-Order Logic kuralları üzerinde fizibilite ve atama kararlarını üretir.
- **Math Layer**: Visibility graph üstünde Dijkstra ile gerçek (obstacle-aware) distance matrix, eigenvector-based centrality skoru, Monte Carlo simülasyonu ile expected delivery success.
- **Optimization Layer**: Genetic Algorithm core'u; Random Assignment ve Nearest Neighbor heuristic baseline'larıyla karşılaştırmalı olarak çalışır.

UI, real-time canvas üzerinde GA'nın generation-by-generation evrilmesini ve final çözüm üzerindeki drone hareketlerini animate eder.

---

## 2. Mimari Genel Bakışı

```
┌─────────────────────────┐         ┌──────────────────────────┐
│   Frontend (React/TS)   │◄───────►│   Backend (FastAPI)      │
│                         │  REST   │                          │
│   - Canvas (Konva.js)   │   +     │   - Data Generator       │
│   - Config Panel        │  WS     │   - Visibility Graph     │
│   - Metrics Panel       │         │   - Logic Engine         │
│   - Animation Engine    │         │   - GA / NN / Random     │
│   - State (Zustand)     │         │   - Monte Carlo          │
└─────────────────────────┘         │   - Evaluation           │
                                    └──────────────────────────┘
                                              │
                                              ▼
                                    ┌──────────────────────┐
                                    │  presets/*.json      │
                                    │  saved_runs/*.json   │
                                    └──────────────────────┘
```

**Data Flow**:
1. User preset seçer veya custom scenario tanımlar → backend `Scenario` objesi yaratır
2. Backend visibility graph + distance matrix precompute eder
3. User "Run Optimization" tetikler → WebSocket bağlantısı açılır
4. Backend her generation'da best chromosome'u WebSocket üzerinden push eder
5. Frontend canvas'ı real-time günceller, convergence chart'ı çizer
6. GA terminates → final solution + KPI'lar hesaplanır
7. User "Play Simulation" → frontend kendi animation engine'iyle drone hareketini render eder

---

## 3. Sentetik Veri Üretimi (Data Generator Module)

### 3.1 Canvas ve Koordinat Sistemi

- **Canvas boyutu**: 1000 × 1000 birim (unitless, soyut 2D düzlem).
- **Ölçek yorumu (sunum/rapor için)**: 1 birim ≈ 10 metre, yani ~10 km × 10 km operasyon alanı.
- **Origin**: sol-üst köşe (0, 0). Y ekseni aşağı doğru artar (canvas convention).
- **Depot**: sabit, koordinat `(500, 500)`.

### 3.2 Reproducibility

Tüm random süreçler tek bir master `seed` parametresinden türetilir. Aynı seed + aynı config → bit-identical output.

```python
np.random.seed(seed)
random.seed(seed)
```

### 3.3 Delivery Points

Delivery noktaları **clustered Gaussian** dağılımıyla üretilir (uniform random olmaz — gerçek şehirlerde teslimat noktaları yığılmıştır, GA'nın convergence davranışı bu yapıdan anlamlı çıktı verir):

**Algoritma**:
1. Cluster sayısı `k`: senaryoya göre `{small: 3, medium: 4, large: 5}`.
2. Cluster center'ları: depot'tan radial uniform — angle `~ U(0, 2π)`, radius `~ U(150, 400)`.
3. Toplam paket sayısı `N` cluster'lara orantılı dağıtılır (her cluster `N/k ± 2`).
4. Her cluster'da paketler: `point ~ N(cluster_center, σ²·I)` where `σ = 70`.
5. Canvas dışına taşan noktalar `[20, 980]` aralığına clip edilir.
6. Depot'a 30 birimden yakın noktalar reddedilir, yeniden örneklenir.

**Her delivery point için generated alanlar**:

| Alan | Değer | Üretim Kuralı |
|------|-------|---------------|
| `id` | `pkg_001` ... `pkg_N` | Sıralı |
| `position` | `(x, y)` | Yukarıdaki algoritma |
| `weight_kg` | float | Truncated `N(2.0, 1.0)`, clip `[0.5, 5.0]` |
| `priority` | `low` / `med` / `high` | Categorical, probabilities `(0.5, 0.3, 0.2)` |
| `time_window_open_min` | int | `~ U(0, 180)` (simülasyon dakikasında açılış) |
| `time_window_duration_min` | int | Express paketler (%20 chance) `~ U(20, 40)`, normal `~ U(60, 120)` |
| `service_time_min` | int | Sabit, 2 dakika |

`time_window_close_min = open_min + duration_min`.

### 3.4 No-Fly Zones

Convex polygon'lar, "düz grid değil" gereksinimini karşılamak için canvas geometrisini bozar.

**Üretim**:
1. Sayı `M`: `{small: 2, medium: 4, large: 6}`.
2. Her polygon için:
   - Center: depot'tan en az 150 birim uzakta, random.
   - Vertex sayısı: `~ U{4, 5, 6}`.
   - "Average radius" `r ~ U(60, 120)`.
   - Vertex'ler polar koordinatta üretilir: angle eşit aralıklı + jitter, radius `r ± 25%`.
   - Convex hull alınır (üretim hatalarına karşı garantör).
3. **Validation rules** (yeniden örnekleme tetikler):
   - Hiçbir polygon depot'u içermez.
   - Hiçbir polygon başka bir polygonla intersect etmez.
   - Hiçbir polygon herhangi bir delivery point'i içermez.
   - Polygon delivery point'lerden en az 10 birim uzaklıkta (numerical safety).

### 3.5 Drone Fleet (Homojen)

Tek bir spec, tüm drone'lara uygulanır:

| Özellik | Değer |
|---------|-------|
| `max_payload_kg` | 5.0 |
| `max_range_per_trip` | 800 birim (≈ 8 km tek şarj) |
| `speed_units_per_min` | 100 (≈ 60 km/h) |
| `service_time_min` | 2 (her teslimatta) |
| `recharge_time_min` | 10 (depo'da multi-trip için) |

Senaryoya göre fleet size: `{small: 3, medium: 4, large: 6}`.

### 3.6 Preset Senaryoları

3 preset JSON olarak `backend/presets/` altında saklanır. Üretim aşamasında data generator çalıştırılır, beğenilen output JSON'a yazılır, sabitlenir.

```
presets/
├── small.json    # 8 packages, 3 drones, 2 no-fly zones, seed=42
├── medium.json   # 18 packages, 4 drones, 4 no-fly zones, seed=137
└── large.json    # 35 packages, 6 drones, 6 no-fly zones, seed=2024
```

### 3.7 Custom Scenario Mode

Kullanıcı UI'dan `N`, `M`, fleet size, seed parametrelerini girip data generator'ı tetikleyebilir. Üretilen scenario session içinde tutulur, "Save" butonu ile `saved_runs/` altına yazılabilir.

---

## 4. Domain Models (Data Schemas)

Tüm modeller Pydantic v2 (backend) ve TypeScript types (frontend) olarak iki tarafta tanımlanır. Frontend tip tanımları backend'den `pydantic-to-typescript` ile generate edilir veya manuel sync tutulur.

### 4.1 Scenario

```python
class Scenario(BaseModel):
    id: str
    name: str
    canvas_width: int = 1000
    canvas_height: int = 1000
    depot: Position  # (500, 500)
    delivery_points: list[DeliveryPoint]
    no_fly_zones: list[NoFlyZone]
    drone_fleet: DroneFleetSpec
    simulation_horizon_min: int = 240
    seed: int
```

### 4.2 DeliveryPoint

```python
class DeliveryPoint(BaseModel):
    id: str
    position: Position
    weight_kg: float
    priority: Literal["low", "med", "high"]
    time_window_open_min: int
    time_window_close_min: int
    service_time_min: int = 2
```

### 4.3 NoFlyZone

```python
class NoFlyZone(BaseModel):
    id: str
    polygon: list[Position]  # convex, CCW ordered
```

### 4.4 DroneFleetSpec

```python
class DroneFleetSpec(BaseModel):
    count: int
    max_payload_kg: float
    max_range_per_trip: float
    speed_units_per_min: float
    recharge_time_min: int
```

### 4.5 Solution

```python
class Trip(BaseModel):
    sequence: list[str]  # delivery point IDs, depot start/end implicit
    distance: float
    duration_min: float

class DroneRoute(BaseModel):
    drone_id: str
    trips: list[Trip]  # multi-trip support

class Solution(BaseModel):
    routes: list[DroneRoute]
    unassigned_packages: list[str]
    total_distance: float
    total_time_min: float
    time_window_violations: int
    capacity_violations: int  # GA repair sonrası 0 olmalı
    fitness: float
    algorithm: Literal["random", "nearest_neighbor", "ga"]
    metadata: dict  # generation count, compute time, vb.
```

---

## 5. Core Compute Modules

### 5.1 Visibility Graph & Distance Matrix Module

**Amaç**: İki nokta arası "drone'un gerçekten uçabileceği" en kısa yolu ve mesafeyi hesaplamak. No-fly zone'lar yüzünden bu, trivial Euclidean değildir.

**Adımlar**:
1. **Node set**: depot + tüm delivery point'ler + tüm no-fly zone polygon vertex'leri.
2. **Edge inşası**: Her node çifti için iki noktayı birleştiren line segment, hiçbir no-fly zone polygon'unun *iç bölgesini* kesmiyorsa edge eklenir. Polygon kenarına teğet geçen segment'lere izin verilir.
3. **Geometric test**: Segment-polygon intersection `shapely` kütüphanesiyle yapılır (`segment.intersects(polygon.boundary)` AND `not polygon.contains(midpoint)`).
4. **Edge weight**: Euclidean distance.
5. **All-pairs shortest path**: NetworkX `all_pairs_dijkstra_path_length` ile depot + delivery point'ler arasındaki distance matrix `D ∈ R^(n+1)×(n+1)` precompute edilir.
6. **Path retrieval**: Animasyon için tam path (vertex sequence) da cache'lenir.

**Output**: `D` matrix, path cache.

### 5.2 Logic Engine Module

**Amaç**: First-Order Logic stilinde rule-based fizibilite ve atama kararları. Custom forward-chaining engine.

**Architecture**:
- `Predicate`: bir koşulu temsil eder (callable returning bool).
- `Rule`: `(antecedents: list[Predicate], consequent: Predicate)`. Tüm antecedent'ler doğru ise consequent inferred olur.
- `KnowledgeBase`: facts (predicate instances) + rules.
- `InferenceEngine`: forward chaining; saturation (no new facts) veya goal achieved'a kadar iterate eder.

**Kural seti** (raporda matematiksel notasyonla yazılacak):

```
R1 (Capacity):
  ∀d ∈ Drones, ∀p ∈ Packages:
    CurrentLoad(d, trip) + Weight(p) ≤ MaxPayload(d) → CanCarry(d, p, trip)

R2 (Range):
  ∀d ∈ Drones, ∀route:
    DistanceTraveled(d, route) + DistToNext(d, p) + DistFromNextToDepot ≤ MaxRange
    → RangeFeasible(d, p, route)

R3 (TimeWindow Soft):
  ∀p ∈ Packages:
    ArrivalTime(p) > CloseTime(p) → TimeWindowViolation(p)
    ArrivalTime(p) < OpenTime(p) → WaitRequired(p)

R4 (NoFlyZone Hard):
  ∀segment ∈ DronePath, ∀z ∈ NoFlyZones:
    Intersects(segment, Interior(z)) → ForbiddenPath(segment)

R5 (MustReturn):
  ∀d ∈ Drones:
    RemainingRange(d) < DistToDepot(d) + SafetyMargin → MustReturn(d)

R6 (Priority Ordering):
  ∀p1, p2 ∈ Packages, same drone, same trip:
    Priority(p1) > Priority(p2) ∧ TimeWindowsCompatible
    → PreferredOrder(p1, p2)
```

**Inference rule kullanımı**: Modus Ponens ve Resolution.
- **Modus Ponens**: kapasite ve range kurallarında doğrudan uygulanır. Raporda örnek bir trace gösterilecek.
- **Resolution**: çelişen atamaları çözmek için (örn. iki yüksek-priority paket aynı drone'a aynı time window'da düşerse).

**Engine kullanımı**:
- GA'nın `decode_chromosome` aşamasında her trip için R1, R2, R5 consult edilir → infeasible chromosome'lar **repair** edilir (paket çıkarılır, sıraya konur).
- R4 distance matrix precompute aşamasında zaten zorlanır (no-fly zone içinden geçen edge'ler graph'a eklenmemiştir).
- R3 fitness penalty olarak hesaplanır.

### 5.3 Genetic Algorithm Module

**Encoding**: Chromosome = `list[list[str]]`. Outer list drone'lar, inner list o drone'a atanmış paket ID'lerinin sırası. Multi-trip split decode aşamasında otomatik yapılır (kapasite/range dolduğunda yeni trip başlar).

**Initialization**:
- Population size `P` (default 50).
- Her chromosome için: paketler random shuffle, drone'lara round-robin dağıtılır. Bu naive init daha iyi convergence için yeterli.
- Population'ın %20'si **NN heuristic** ile seed edilir (seeded GA literatüründe standart, convergence'i hızlandırır).

**Fitness function** (minimization):

```
F(chromosome) = w₁·total_distance
              + w₂·(time_window_violations × penalty_per_violation)
              + w₃·(unassigned_count × penalty_per_unassigned)
```

Default weights: `w₁ = 1.0, w₂ = 50.0, w₃ = 500.0`. Penalty per violation: 100. UI'dan tunable.

GA dahili olarak `1 / (F + ε)` maksimize eder.

**Selection**: Tournament, size `k = 3`. Random `k` chromosome çekilir, en iyisi seçilir.

**Crossover**: **Best Cost Route Crossover (BCRC)**, VRP literatür standardı.
1. Parent A ve B'den her birinden bir route seçilir.
2. A'nın seçili route'undaki paketler B'den çıkarılır (ve tersi).
3. Çıkarılan paketler, **best insertion** ile receiver parent'a yerleştirilir (her insertion için marginal cost minimum olan pozisyon).
- Crossover rate (default 0.8).

**Mutation operatörleri** (her biri belli bir olasılıkla):
- **Swap mutation** (intra-route): aynı route'da iki paket yer değiştirir. Prob 0.3.
- **Relocate mutation** (inter-route): bir paket bir route'tan başka route'a taşınır. Prob 0.4.
- **2-opt** (intra-route): route'un bir segmenti ters çevrilir. TSP'nin klasik local search'ü. Prob 0.3.

Overall mutation rate (chromosome başına en az bir mutation tetiklenme olasılığı): default 0.15.

**Repair operator**: Decode sırasında capacity/range ihlali olan paketler **unassigned pool**'a atılır, sonra **best insertion** ile yeniden yerleştirilmeye çalışılır. Yerleşemeyenler `unassigned` olarak kalır ve fitness penalty alır.

**Elitism**: Top 2 chromosome korunur (configurable).

**Termination**:
- Max generations `G` (default 200).
- Convergence: 50 generation boyunca best fitness improvement < 0.5%.

**Output stream**: Her generation sonunda `(generation_idx, best_fitness, best_chromosome)` WebSocket üzerinden frontend'e push edilir.

### 5.4 Baseline Algorithms Module

#### 5.4.1 Random Assignment

- Paketleri shuffle et.
- Round-robin drone'lara dağıt.
- Decode + repair.

#### 5.4.2 Nearest Neighbor Heuristic

```
For each drone d:
  current = depot
  while drone has range/capacity AND unassigned packages exist:
    next = argmin{ distance(current, p) | p ∈ unassigned, feasible(d, p) }
    if next is None: drone returns to depot (new trip if range allows)
    else: assign next to d, current = next
```

Hızlı ve deterministic. GA'nın seeding'inde de kullanılır.

#### 5.4.3 Karşılaştırma protokolü

Aynı scenario üstünde üç algoritma da çalıştırılır. GA stochastic olduğu için **30 run × farklı seed** ile çalışır, mean ± std raporlanır. Random ve NN tek run.

### 5.5 Monte Carlo Simulation Module (Probability Layer)

**Amaç**: Final solution'ın "expected delivery success" oranını probabilistic olarak hesaplamak. Probability gereksiniminin gerçek bir AI tekniği olarak karşılanması.

**Model**: Her uçuş segmenti için bağımsız failure event:
- `P(segment_failure) = α · (segment_length / max_range)` where `α = 0.02` (low base failure rate).
- Trip başarılı sayılır iff tüm segment'leri başarılı.
- Solution-level metric: `expected_success_rate = E[successful_deliveries / total_packages]`.

**Algoritma**:
- 1000 Monte Carlo iteration.
- Her iteration'da her segment için Bernoulli sample.
- Sonuçların mean ve %95 confidence interval'ı raporlanır.

**Output**: `expected_success_rate ± CI`, KPI panelinde gösterilir.

### 5.6 Linear Algebra Layer (Centrality Score)

**Amaç**: Linear algebra gereksinimini eigenvector hesabıyla zenginleştirmek; raporda matematiksel ağırlık.

**Hesap**:
1. Distance matrix `D`'den similarity matrix: `S = exp(-D / σ)`, σ = mean(D).
2. Row-normalize → stochastic matrix `P`.
3. **Power iteration** ile dominant eigenvector hesaplanır → her delivery point için "centrality score".
4. Ek olarak: distance matrix'in **Frobenius norm**'u raporlanır ("scenario complexity proxy").

UI'da centrality score'lar delivery point'lerin renk yoğunluğuna mapping yapılır (toggle).

### 5.7 Evaluation & Metrics Module

**Solution-level metrics**:
- `total_distance` (sum across all drones)
- `total_time_min` (max across drones — paralel uçuş)
- `time_window_violations` (count + total minutes over)
- `unassigned_packages` (count)
- `capacity_violations` (post-repair, should be 0)
- `expected_success_rate` (Monte Carlo)
- `fitness` (fitness function output)

**Algorithm-level metrics** (comparison için):
- `compute_time_seconds`
- `convergence_generation` (GA only — when 50-gen plateau hit)
- `improvement_over_random` (%)

**Statistical reporting** (rapor için):
- 30-run GA: mean ± std for each metric.
- Box plots: distance, fitness distribution.
- Convergence curves: best fitness vs generation, mean ± std band.

---

## 6. Backend API

### 6.1 REST Endpoints

```
GET    /api/presets                  → list of preset scenario IDs
GET    /api/presets/{id}             → full Scenario object
POST   /api/scenarios/generate       → body: {n_packages, n_zones, fleet_size, seed}
                                      → returns: Scenario
POST   /api/scenarios/save           → save custom scenario to disk
GET    /api/scenarios/{id}/distance_matrix   → precomputed D matrix + paths
POST   /api/optimize/random          → body: {scenario_id, seed} → Solution
POST   /api/optimize/nearest_neighbor → body: {scenario_id} → Solution
POST   /api/optimize/ga              → body: {scenario_id, ga_params, seed}
                                      → returns: run_id (then connect WebSocket)
GET    /api/runs/{run_id}            → full result + history
POST   /api/monte_carlo              → body: {solution_id, n_iters} → MC result
```

### 6.2 WebSocket Endpoint

```
WS  /ws/optimize/ga/{run_id}
```

**Server → Client messages**:

```json
// Per generation
{
  "type": "generation",
  "generation": 42,
  "best_fitness": 1284.5,
  "mean_fitness": 1502.3,
  "best_solution": { /* Solution */ }
}

// On termination
{
  "type": "complete",
  "final_solution": { /* Solution */ },
  "compute_time_seconds": 23.4,
  "convergence_generation": 142
}
```

**Client → Server**:
```json
{ "type": "cancel" }   // user aborts run
```

### 6.3 Throughput Considerations

- GA'nın WebSocket push frequency'si: her generation'da bir kez. Large scenario'da generation ~50ms sürer; bu rate frontend için manageable.
- Best chromosome JSON serialization payload'ı: ~5-15 KB. Large scenario'da bile sorun değil.
- WebSocket heartbeat: 30 saniyede bir.

---

## 7. Frontend Application

### 7.1 Layout (Desktop, min 1280×720)

```
┌────────────────────────────────────────────────────────────────────┐
│  TOP BAR: Logo | Preset Dropdown | Custom Scenario | Run | Reset   │
├──────────────┬───────────────────────────────────────┬─────────────┤
│              │                                       │             │
│   LEFT       │             CANVAS                    │   RIGHT     │
│   PANEL      │         (Konva.js stage)              │   PANEL     │
│              │                                       │             │
│   Config     │   - No-fly zones (red poly)           │   Live      │
│   Sections:  │   - Depot (orange star)               │   Metrics:  │
│   - Algo     │   - Delivery points (color = prio)    │   - Gen / G │
│   - Weights  │   - Visibility graph (toggle)         │   - Fitness │
│   - Seed     │   - Drone routes (color per drone)    │   - Conv    │
│   - Compare  │   - Drone agents (animated)           │     chart   │
│              │   - Centrality heatmap (toggle)       │   - KPIs    │
│              │                                       │             │
├──────────────┴───────────────────────────────────────┴─────────────┤
│  BOTTOM PANEL (collapsible): Algorithm Comparison Table + Logs     │
└────────────────────────────────────────────────────────────────────┘
```

### 7.2 Canvas Rendering (Konva.js)

**Layer hierarchy** (alt → üst):
1. **Background layer**: grid lines (light grey, 100-unit spacing), canvas border.
2. **No-fly zone layer**: filled polygon, `rgba(220, 38, 38, 0.25)`, kenarlık `#dc2626`.
3. **Visibility graph layer** (toggleable, debug): tüm edges, `rgba(100, 100, 100, 0.15)`.
4. **Centrality heatmap layer** (toggleable): delivery point'ler eigenvector skoruna göre kırmızı→sarı gradient ile renklenir.
5. **Delivery points layer**:
   - Circle, radius `8 + 2·weight_kg` (weight'i görselleştirir).
   - Border color: priority — `low: #94a3b8, med: #f59e0b, high: #ef4444`.
   - Label (hover): id, weight, priority, time window.
6. **Depot layer**: large star (size 20), color `#f97316`, label "DEPOT".
7. **Routes layer**:
   - Her drone'a unique color (palette: 6 distinguishable colors).
   - Polyline: depot → p1 → p2 → ... → depot, no-fly zone polygon vertex'lerinden geçer (precomputed path).
   - Trip ayrımı: aynı drone'un farklı trip'leri farklı stroke style ile (dashed for trip 2, dotted for trip 3).
   - Arrow head her segment sonunda.
8. **Drone agents layer** (animation only): triangle marker, drone'un current position'ında. Smooth interpolation.

**Interaktif öğeler**:
- Pan & zoom (mouse wheel).
- Hover delivery point → tooltip.
- Click delivery point → highlight assigned drone'un route'u.
- Toggle butonları: visibility graph, centrality heatmap, trip numbers.

### 7.3 Configuration Panel (Sol)

Sectioned UI, accordion stili:

**Section 1: Scenario**
- Preset dropdown: small / medium / large / custom.
- "Generate Custom" butonu (opens modal): n_packages, n_zones, fleet_size, seed inputs.

**Section 2: Algorithm Selection**
- Checkboxes: Random / Nearest Neighbor / GA. Default: hepsi seçili.

**Section 3: GA Parameters** (collapse default open)
- Population size (slider, 20-200, default 50)
- Generations (slider, 50-500, default 200)
- Mutation rate (slider, 0.01-0.5, default 0.15)
- Crossover rate (slider, 0.5-1.0, default 0.8)
- Tournament size (number, 2-10, default 3)
- Elitism count (number, 0-5, default 2)

**Section 4: Fitness Weights**
- w₁ distance (default 1.0)
- w₂ time window violation (default 50.0)
- w₃ unassigned penalty (default 500.0)

**Section 5: Reproducibility**
- Random seed (number input, default 42)

**Section 6: Visualization Toggles**
- Show visibility graph
- Show centrality heatmap
- Show trip numbers
- Animation speed (slider, 1× - 10×)

### 7.4 Metrics Panel (Sağ)

**Live during GA run**:
- Generation progress bar (current / max)
- Best fitness (large number, animated)
- Mean fitness (smaller)
- Convergence chart (Recharts line, x=generation, y=fitness, two lines: best + mean)
- Estimated time remaining

**Post-run KPI table**:
| Metric | Random | NN | GA |
|--------|--------|----|----|
| Total Distance | ... | ... | ... |
| Total Time (min) | ... | ... | ... |
| TW Violations | ... | ... | ... |
| Unassigned | ... | ... | ... |
| Expected Success | ... | ... | ... |
| Compute Time (s) | ... | ... | ... |

GA satırı 30-run mean ± std olarak gösterilir.

### 7.5 Animation Engine (Frontend)

GA tamamlandıktan sonra "Play Simulation" butonu enabled olur. Animation engine:

1. Final solution'dan her drone için **timeline** çıkarır:
   - `t=0`: drone depot'ta.
   - Her segment için `t_arrive`, `t_depart` (= `t_arrive + service_time`).
   - Multi-trip için recharge time eklenir.
2. Global simulation clock `t` user-controllable speed ile ilerler.
3. Her frame'de her drone'un position'ı: aktif segment üstünde `t` parametresine göre linear interpolation. Segment, no-fly zone polygon vertex'lerinden geçen polyline ise, ara vertex'ler arasında interpolation yapılır.
4. Service zamanında drone delivery point'in üstünde duraklar, küçük bir "pulse" efekti (radius ripple).
5. Her teslimat sonrası top-left'te toast: "Drone 2 delivered pkg_07 at 14:23".
6. Tüm teslimatlar tamamlandığında "Simulation Complete" overlay.

Speed control: 1× (real-time, 240 dakika = 4 saat), 5×, 10×, 30× (8 dakikada tamamlanır).

### 7.6 State Management (Zustand)

```typescript
interface AppState {
  scenario: Scenario | null
  distanceMatrix: number[][] | null
  visibilityPaths: Record<string, Position[]> | null
  currentRun: {
    runId: string
    algorithm: 'random' | 'nn' | 'ga'
    status: 'idle' | 'running' | 'complete'
    progress: number
    history: Array<{ gen: number; bestFitness: number; meanFitness: number }>
  } | null
  solutions: {
    random?: Solution
    nn?: Solution
    ga?: Solution
  }
  config: GAConfig & FitnessWeights & { seed: number }
  visualization: {
    showVisibilityGraph: boolean
    showCentrality: boolean
    showTripNumbers: boolean
    animationSpeed: number
  }
  animation: {
    isPlaying: boolean
    currentTime: number
    dronePositions: Record<string, Position>
  }
}
```

---

## 8. End-to-End User Flow

1. **Scenario Selection**:
   - User uygulamayı açar, default olarak "medium" preset yüklü gelir.
   - Canvas'ta delivery points, depot, no-fly zones render edilir.

2. **Distance Matrix Computation** (transparent to user):
   - Backend visibility graph + Dijkstra çalıştırır. ~200-500ms.
   - Eigenvector centrality hesaplanır.
   - Frontend cache'ler, paths çizilebilir hale gelir.

3. **Configuration**:
   - User left panel'den GA parametreleri ve fitness weights ayarlar.
   - Seed default 42, isterse değiştirir.

4. **Optimization Run**:
   - User "Run Optimization" tıklar.
   - Backend Random + NN'i instant çalıştırır, sonuçları döner.
   - GA WebSocket bağlantısı açılır.
   - Her generation'da:
     - Backend → frontend: best chromosome + fitness.
     - Frontend canvas'ta routes'u günceller (smooth transition önceki generation'dan yeni'sine).
     - Convergence chart yeni point ekler.
   - GA tamamlandığında 30-run automatic batch tetiklenir (mean ± std için), arka planda.

5. **Result Inspection**:
   - KPI table dolar.
   - Comparison panel'de winner highlight edilir.
   - User algorithm'ları toggle edip canvas üstünde rotalarını karşılaştırır.

6. **Simulation Playback**:
   - User "Play Simulation" tıklar.
   - Drone agents canvas üstünde animate olur.
   - Toast'lar her teslimatı bildirir.

7. **Export** (opsiyonel):
   - "Export Run" butonu solution + scenario + config'i JSON olarak indirir.
   - Rapor için screenshot / video kaydı bu aşamada alınır.

---

## 9. Configuration Parameters (Defaults)

| Parameter | Default | Range |
|-----------|---------|-------|
| `seed` | 42 | int |
| `ga.population_size` | 50 | 20-200 |
| `ga.generations` | 200 | 50-500 |
| `ga.mutation_rate` | 0.15 | 0.01-0.5 |
| `ga.crossover_rate` | 0.8 | 0.5-1.0 |
| `ga.tournament_size` | 3 | 2-10 |
| `ga.elitism` | 2 | 0-5 |
| `ga.convergence_patience` | 50 | 10-100 |
| `ga.nn_seed_ratio` | 0.20 | 0.0-0.5 |
| `fitness.w_distance` | 1.0 | 0.1-10 |
| `fitness.w_time_violation` | 50.0 | 0-500 |
| `fitness.w_unassigned` | 500.0 | 0-5000 |
| `monte_carlo.iterations` | 1000 | 100-10000 |
| `monte_carlo.alpha` | 0.02 | 0.0-0.1 |
| `simulation.horizon_min` | 240 | fixed |
| `drone.safety_margin_units` | 50 | fixed |

---

## 10. Tech Stack & Dependencies

### Backend (Python 3.11+)

```
fastapi>=0.110
uvicorn[standard]>=0.27
pydantic>=2.6
numpy>=1.26
networkx>=3.2
shapely>=2.0
scipy>=1.12
websockets>=12.0
python-multipart  # for file uploads
pytest>=8.0      # for unit tests
```

### Frontend

```json
{
  "dependencies": {
    "react": "^18.3.0",
    "react-dom": "^18.3.0",
    "konva": "^9.3.0",
    "react-konva": "^18.2.10",
    "recharts": "^2.12.0",
    "zustand": "^4.5.0",
    "socket.io-client": "^4.7.0",
    "axios": "^1.6.0",
    "tailwindcss": "^3.4.0"
  },
  "devDependencies": {
    "vite": "^5.2.0",
    "typescript": "^5.4.0",
    "@types/react": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.0"
  }
}
```

NOT: WebSocket için socket.io yerine native `WebSocket` API de kullanılabilir (FastAPI native WS ile uyumlu, socket.io ekstra layer). Native daha az dependency.

---

## 11. Project Structure

```
drone-routing-system/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                    # FastAPI app + CORS + router include
│   │   ├── config.py                  # default params
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   ├── scenarios.py           # REST: presets, generate, save
│   │   │   ├── optimization.py        # REST + WS: run algorithms
│   │   │   └── monte_carlo.py
│   │   ├── core/
│   │   │   ├── __init__.py
│   │   │   ├── data_generator.py      # Section 3
│   │   │   ├── visibility_graph.py    # Section 5.1
│   │   │   ├── distance_matrix.py     # uses visibility_graph
│   │   │   ├── logic_engine.py        # Section 5.2 (custom)
│   │   │   ├── rules.py               # R1-R6 definitions
│   │   │   ├── genetic_algorithm.py   # Section 5.3
│   │   │   ├── ga_operators.py        # crossover, mutation, selection
│   │   │   ├── baseline_algorithms.py # Section 5.4
│   │   │   ├── monte_carlo.py         # Section 5.5
│   │   │   ├── linear_algebra.py      # Section 5.6
│   │   │   └── evaluation.py          # Section 5.7
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   ├── scenario.py            # Pydantic
│   │   │   ├── solution.py
│   │   │   └── ga_config.py
│   │   └── utils/
│   │       └── geometry.py            # segment-polygon helpers
│   ├── presets/
│   │   ├── small.json
│   │   ├── medium.json
│   │   └── large.json
│   ├── saved_runs/                    # gitignored
│   ├── tests/
│   │   ├── test_data_generator.py
│   │   ├── test_visibility_graph.py
│   │   ├── test_logic_engine.py
│   │   ├── test_ga.py
│   │   └── test_evaluation.py
│   ├── requirements.txt
│   └── README.md
│
├── frontend/
│   ├── src/
│   │   ├── main.tsx
│   │   ├── App.tsx
│   │   ├── components/
│   │   │   ├── Canvas/
│   │   │   │   ├── CanvasStage.tsx
│   │   │   │   ├── DepotMarker.tsx
│   │   │   │   ├── DeliveryPoint.tsx
│   │   │   │   ├── NoFlyZonePolygon.tsx
│   │   │   │   ├── RouteLayer.tsx
│   │   │   │   ├── DroneAgent.tsx
│   │   │   │   ├── VisibilityGraphLayer.tsx
│   │   │   │   └── CentralityHeatmap.tsx
│   │   │   ├── ConfigPanel/
│   │   │   │   ├── ConfigPanel.tsx
│   │   │   │   ├── ScenarioSection.tsx
│   │   │   │   ├── GAParamsSection.tsx
│   │   │   │   └── WeightsSection.tsx
│   │   │   ├── MetricsPanel/
│   │   │   │   ├── MetricsPanel.tsx
│   │   │   │   ├── ConvergenceChart.tsx
│   │   │   │   └── KPITable.tsx
│   │   │   ├── ComparisonPanel/
│   │   │   │   └── ComparisonTable.tsx
│   │   │   └── TopBar/
│   │   │       └── TopBar.tsx
│   │   ├── hooks/
│   │   │   ├── useWebSocket.ts
│   │   │   ├── useAnimation.ts
│   │   │   └── useScenario.ts
│   │   ├── store/
│   │   │   └── appStore.ts            # Zustand
│   │   ├── api/
│   │   │   ├── client.ts              # axios instance
│   │   │   ├── scenarios.ts
│   │   │   └── optimization.ts
│   │   ├── types/
│   │   │   └── domain.ts              # Scenario, Solution, etc.
│   │   └── styles/
│   │       └── tailwind.css
│   ├── public/
│   ├── index.html
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── tailwind.config.js
│   ├── package.json
│   └── README.md
│
├── docs/
│   ├── report.md                      # Final akademik rapor
│   ├── architecture.md
│   └── algorithm_traces.md            # Modus Ponens / Resolution örnekleri
│
├── scripts/
│   ├── generate_presets.py            # data_generator + JSON dump
│   └── benchmark.py                   # 30-run GA batch
│
├── .gitignore
└── README.md
```

---

## 12. Deliverables Checklist

### Çalışan Sistem
- [ ] Backend FastAPI app, tüm endpoint'ler
- [ ] Frontend React app, tüm panel'ler ve canvas
- [ ] 3 preset JSON dosyası
- [ ] WebSocket real-time GA streaming
- [ ] Animation engine (final solution playback)

### Algoritma Implementasyonları
- [ ] Visibility graph + Dijkstra distance matrix
- [ ] Custom forward-chaining logic engine + 6 kural
- [ ] Genetic Algorithm (BCRC crossover + 3 mutation + repair)
- [ ] Random + Nearest Neighbor baselines
- [ ] Monte Carlo expected success rate
- [ ] Eigenvector centrality (power iteration)

### Doğrulama
- [ ] 30-run GA benchmark on medium preset, mean ± std reported
- [ ] Modus Ponens trace example documented
- [ ] Resolution trace example documented
- [ ] Convergence plot for all 3 presets

### Rapor (akademik)
- [ ] Logic kuralları matematiksel notasyon
- [ ] Math layer derivations (eigenvector, expected value)
- [ ] GA pseudocode
- [ ] Comparison table (3 algoritma × 3 preset)
- [ ] Architecture diagram
- [ ] Future work section

### Demo Materyali
- [ ] 7-dakika sunum slide'ları
- [ ] Backup video (full run-through, 3 presets)
- [ ] Video upload (YouTube unlisted veya GDrive)

---

## 13. Notlar ve Kapsam Riski Yönetimi

**Kapsamı genişletme yasaktır** — aşağıdakiler bu PRD'nin dışındadır, eklemeyin:
- Dinamik paket gelişi / online re-optimization
- Heterojen drone fleet
- Multi-depot
- Real-time weather updates
- Authentication, multi-user, persistence db (sadece JSON file persistence)
- Mobile responsive (desktop-first, min 1280×720)

**Sıkışırsa fedaya açık olanlar** (öncelik sırasıyla):
1. Eigenvector centrality heatmap (sadece sayı raporlanır, görselleştirme atılır)
2. Monte Carlo'yu basit expected value'ya indir (1000 iter yerine analytical)
3. Visibility graph toggle'ı atılır (debug-only)
4. Custom scenario generation UI atılır (sadece preset'ler)

**Asla feda edilmeyecekler**:
- Logic engine + 6 kural
- GA core (crossover + mutation + repair)
- Random + NN baselines
- Distance matrix (visibility graph zorunlu, no-fly zone bypass yok)
- Real-time GA streaming (animation atılırsa final solution polyline yeterli)

---

**End of PRD v1.0**
