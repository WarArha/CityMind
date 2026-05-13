"""
CityMind - Challenge 5: Crime Risk Prediction and Integration
=============================================================
Authors: Group Project - BS Computer Science

PIPELINE (two distinct learning types):

  PHASE 1 — K-Means Clustering (UNSUPERVISED)
    Input : node features (population density, industrial proximity)
    Output: cluster label per node (no pre-labelled data used)
    Why unsupervised? We have no crime labels at this point.
    K-Means groups nodes by similarity without being told the answers.

  PHASE 2 — Random Forest Classification (SUPERVISED) — implemented from scratch
    Input : synthetic crime dataset (node features + generated risk labels)
    Output: trained model that predicts High / Medium / Low risk
    Why supervised? We now have labels (synthetically generated) and
    want a model that generalises to unseen nodes during simulation.

  PHASE 3 — Integration into shared CityGraph
    city.risk_index[nid] updated for every node.
    Challenge 3 GA (ambulance) and Challenge 4 A* both read this value.
    High-risk areas have higher effective travel cost → system responds.

SYNTHETIC CRIME LOGIC (justified):
  Crime is modelled as a weighted sum of:
    - Industrial proximity  (weight 0.40) — crime clusters near industrial zones
    - Population density    (weight 0.35) — more people = more crime opportunity
    - Location type risk    (weight 0.25) — type-specific baseline risk

WHY K-MEANS OVER HIERARCHICAL CLUSTERING:
  We know the number of groups (K=3: High/Medium/Low).
  Hierarchical clustering does not require K upfront but produces a
  dendrogram that must be manually cut to extract flat clusters, adding
  an arbitrary decision step. It is also computationally expensive on
  large grids. K-Means is faster, simpler, and maps naturally to our
  three risk levels.

WHY RANDOM FOREST OVER DECISION TREE:
  Decision Trees overfit on small synthetic datasets.
  Random Forest averages over many trees on random bootstrap samples
  and random feature subsets, reducing variance and producing more
  reliable predictions. It also provides feature importances showing
  which factors drive crime risk — useful for the viva.
  Implemented entirely from scratch without any external libraries.
"""

import random
import math
import heapq
from collections import deque, Counter


# ── Constants ─────────────────────────────────────────────────────
NUM_CLUSTERS  = 3
NUM_OFFICERS  = 10
RISK_LABELS   = ["Low", "Medium", "High"]
RISK_VALUES   = {"Low": 0.1, "Medium": 0.4, "High": 0.8}

POP_BY_TYPE = {
    "Residential":    800,
    "Hospital":       150,
    "School":         300,
    "Industrial":     200,
    "PowerPlant":      50,
    "AmbulanceDepot":  30,
}

BASE_RISK_BY_TYPE = {
    "Residential":    0.50,
    "Industrial":     0.65,
    "School":         0.25,
    "Hospital":       0.20,
    "PowerPlant":     0.10,
    "AmbulanceDepot": 0.15,
}


# ── BFS shortest-path helper ──────────────────────────────────────
def bfs_hops(city, start: int, targets: set) -> float:
    if start in targets:
        return 0.0
    visited = {start}
    queue   = deque([(start, 0)])
    while queue:
        node, hops = queue.popleft()
        neighbours = []
        if city.roads:
            for nb, edge in city.roads.get(node, {}).items():
                if isinstance(edge, dict) and not edge.get("blocked", False):
                    neighbours.append(nb)
                elif not isinstance(edge, dict):
                    neighbours.append(nb)
        else:
            neighbours = city.neighbors(node)
        for nb in neighbours:
            if nb not in visited and city.assignment.get(nb) is not None:
                visited.add(nb)
                if nb in targets:
                    return float(hops + 1)
                queue.append((nb, hops + 1))
    return float("inf")


# ── Feature extraction ────────────────────────────────────────────
def extract_features(city) -> dict:
    """
    For every active node, extract a feature vector:
      [0] norm_population   — population density normalised 0..1
      [1] ind_proximity     — inverse industrial proximity (closer=higher)
      [2] type_risk         — base crime rate from BASE_RISK_BY_TYPE
      [3] degree            — fraction of max possible neighbours (0..1)
    """
    active = [n for n in city.active_nodes
              if city.assignment.get(n) is not None]
    if not active:
        return {}

    industrials = {n for n in active
                   if city.assignment.get(n) == "Industrial"}

    features = {}
    max_degree = 4.0

    for nid in active:
        loc = city.assignment.get(nid, "Residential")

        pop      = POP_BY_TYPE.get(loc, 100)
        norm_pop = pop / 800.0

        if industrials:
            hops     = bfs_hops(city, nid, industrials)
            ind_prox = 1.0 / (1.0 + hops)
        else:
            ind_prox = 0.0

        type_risk = BASE_RISK_BY_TYPE.get(loc, 0.3)

        neighbours = [nb for nb in city.neighbors(nid)
                      if city.assignment.get(nb) is not None]
        degree = len(neighbours) / max_degree

        features[nid] = [norm_pop, ind_prox, type_risk, degree]

    return features


# ─────────────────────────────────────────────────────────────────
#  PHASE 1 — K-MEANS CLUSTERING (written from scratch)
# ─────────────────────────────────────────────────────────────────
class KMeans:
    """
    K-Means clustering implemented from scratch.

    VIVA EXPLANATION:
      1. Initialise K centroids using K-Means++ (spread out initial centroids)
      2. Assign each point to its nearest centroid (Euclidean distance)
      3. Recompute each centroid as the mean of its assigned points
      4. Repeat 2-3 until assignments stop changing (convergence)
      5. Run n_init times and keep the run with lowest inertia
    """

    def __init__(self, k: int = NUM_CLUSTERS, max_iter: int = 100, n_init: int = 5):
        self.k        = k
        self.max_iter = max_iter
        self.n_init   = n_init
        self.centroids = []
        self.labels_   = {}

    def _euclidean(self, a: list, b: list) -> float:
        return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))

    def _assign(self, points: dict) -> dict:
        labels = {}
        for nid, feat in points.items():
            dists       = [self._euclidean(feat, c) for c in self.centroids]
            labels[nid] = dists.index(min(dists))
        return labels

    def _update_centroids(self, points: dict, labels: dict) -> list:
        dim = len(next(iter(points.values())))
        new_centroids = []
        for k in range(self.k):
            cluster_pts = [points[n] for n, lbl in labels.items() if lbl == k]
            if not cluster_pts:
                new_centroids.append(random.choice(list(points.values()))[:])
            else:
                mean = [sum(p[d] for p in cluster_pts) / len(cluster_pts)
                        for d in range(dim)]
                new_centroids.append(mean)
        return new_centroids

    def _inertia(self, points: dict, labels: dict) -> float:
        total = 0.0
        for nid, feat in points.items():
            c      = self.centroids[labels[nid]]
            total += self._euclidean(feat, c) ** 2
        return total

    def fit(self, points: dict):
        if not points:
            return self
        keys   = list(points.keys())
        pts_2d = {n: points[n][:2] for n in keys}

        best_labels    = None
        best_inertia   = float("inf")
        best_centroids = None

        for _ in range(self.n_init):
            # K-Means++ initialisation
            self.centroids = [random.choice(list(pts_2d.values()))[:]]
            for _ in range(self.k - 1):
                dists = [min(self._euclidean(p, c) for c in self.centroids)
                         for p in pts_2d.values()]
                total = sum(dists)
                if total > 0:
                    r     = random.uniform(0, total)
                    cumul = 0.0
                    chosen = list(pts_2d.values())[-1]
                    for p, d in zip(pts_2d.values(), dists):
                        cumul += d
                        if cumul >= r:
                            chosen = p[:]; break
                    self.centroids.append(chosen)
                else:
                    self.centroids.append(random.choice(list(pts_2d.values()))[:])

            labels = {}
            for _ in range(self.max_iter):
                new_labels = self._assign(pts_2d)
                if new_labels == labels:
                    break
                labels          = new_labels
                self.centroids  = self._update_centroids(pts_2d, labels)

            inertia = self._inertia(pts_2d, labels)
            if inertia < best_inertia:
                best_inertia   = inertia
                best_labels    = dict(labels)
                best_centroids = [c[:] for c in self.centroids]

        self.centroids = best_centroids
        self.labels_   = best_labels
        return self


def label_clusters(km: KMeans, features: dict) -> dict:
    """
    Map K-Means cluster indices to risk labels (High/Medium/Low).
    The cluster with the highest mean (population + industrial proximity)
    gets labelled 'High', etc.
    """
    cluster_scores = {}
    cluster_counts = {}
    for nid, lbl in km.labels_.items():
        feat  = features[nid]
        score = feat[0] + feat[1]
        cluster_scores[lbl] = cluster_scores.get(lbl, 0.0) + score
        cluster_counts[lbl] = cluster_counts.get(lbl, 0) + 1

    avg_scores = {k: cluster_scores[k] / cluster_counts[k]
                  for k in cluster_scores}

    sorted_clusters   = sorted(avg_scores, key=lambda k: avg_scores[k], reverse=True)
    cluster_to_risk   = {}
    for rank, cluster_idx in enumerate(sorted_clusters):
        cluster_to_risk[cluster_idx] = RISK_LABELS[
            len(RISK_LABELS) - 1 - rank]

    return {nid: cluster_to_risk[lbl] for nid, lbl in km.labels_.items()}


# ─────────────────────────────────────────────────────────────────
#  SYNTHETIC CRIME DATASET GENERATION
# ─────────────────────────────────────────────────────────────────
def generate_synthetic_dataset(city, features: dict, cluster_risk: dict) -> list:
    """
    Generate synthetic training data for the Random Forest.
    score = 0.40 * ind_proximity + 0.35 * norm_population + 0.25 * type_base_risk
    Add Gaussian noise then threshold to High / Medium / Low.
    """
    dataset = []
    for nid, feat in features.items():
        norm_pop  = feat[0]
        ind_prox  = feat[1]
        type_risk = feat[2]

        score = 0.40 * ind_prox + 0.35 * norm_pop + 0.25 * type_risk
        noise = random.gauss(0, 0.05)
        score = max(0.0, min(1.0, score + noise))

        if score >= 0.55:
            label = "High"
        elif score >= 0.30:
            label = "Medium"
        else:
            label = "Low"

        dataset.append((feat, label))

    return dataset


# ─────────────────────────────────────────────────────────────────
#  PHASE 2 — RANDOM FOREST (implemented from scratch, no sklearn)
# ─────────────────────────────────────────────────────────────────

class _DTNode:
    """A single node in a Decision Tree."""
    __slots__ = ("feature", "threshold", "left", "right", "label")

    def __init__(self):
        self.feature   = None   # feature index used for split
        self.threshold = None   # split threshold value
        self.left      = None   # left child _DTNode (feature <= threshold)
        self.right     = None   # right child _DTNode (feature > threshold)
        self.label     = None   # set only on leaf nodes (majority class)


class _DecisionTree:
    """
    A single Decision Tree using Gini impurity splits.

    VIVA EXPLANATION:
      - At each node, we try every possible split on a random subset of features
      - We pick the split that gives the greatest reduction in Gini impurity
      - Gini impurity = 1 - sum(p_i^2) where p_i is the fraction of class i
      - We stop splitting when max_depth is reached or a node is pure
      - Leaf prediction = majority class of training samples at that node
    """

    def __init__(self, max_depth: int = 5, min_samples_split: int = 2,
                 n_features_split: int = None):
        self.max_depth         = max_depth
        self.min_samples_split = min_samples_split
        self.n_features_split  = n_features_split  # how many features to try at each split
        self.root              = None
        self.n_total_features  = 0
        # feature_idx -> total weighted gini drop (for importance calculation)
        self.feature_importance_raw = {}

    def _gini(self, y: list) -> float:
        """Gini impurity of label list y."""
        n = len(y)
        if n == 0:
            return 0.0
        counts = Counter(y)
        return 1.0 - sum((c / n) ** 2 for c in counts.values())

    def _best_split(self, X: list, y: list, feat_indices: list):
        """
        Try all thresholds for each feature in feat_indices.
        Return (best_feature, best_threshold, left_indices, gain).
        Returns (None, None, None, -1) if no beneficial split found.
        """
        best_gain   = -1.0
        best_feat   = None
        best_thresh = None
        best_left   = None

        parent_gini = self._gini(y)
        n           = len(y)

        for feat in feat_indices:
            # Collect unique values and form midpoint thresholds
            vals = sorted(set(row[feat] for row in X))
            if len(vals) == 1:
                continue
            thresholds = [(vals[i] + vals[i + 1]) / 2.0 for i in range(len(vals) - 1)]

            for thresh in thresholds:
                left_idx  = [i for i, row in enumerate(X) if row[feat] <= thresh]
                right_idx = [i for i in range(n) if i not in set(left_idx)]

                if not left_idx or not right_idx:
                    continue

                y_left  = [y[i] for i in left_idx]
                y_right = [y[i] for i in right_idx]

                weighted = (len(y_left) / n)  * self._gini(y_left) + \
                           (len(y_right) / n) * self._gini(y_right)
                gain = parent_gini - weighted

                if gain > best_gain:
                    best_gain   = gain
                    best_feat   = feat
                    best_thresh = thresh
                    best_left   = left_idx

        return best_feat, best_thresh, best_left, best_gain

    def _build(self, X: list, y: list, depth: int) -> _DTNode:
        node          = _DTNode()
        node.label    = Counter(y).most_common(1)[0][0]  # default leaf

        # Stop conditions
        if (depth >= self.max_depth or
                len(y) < self.min_samples_split or
                len(set(y)) == 1):
            return node

        # Random feature subset (sqrt heuristic used by Random Forest)
        k          = self.n_features_split or self.n_total_features
        feat_subset = random.sample(range(self.n_total_features),
                                    min(k, self.n_total_features))

        feat, thresh, left_idx, gain = self._best_split(X, y, feat_subset)

        if feat is None or gain <= 1e-9:
            return node  # no beneficial split — stay as leaf

        # Track importance: weighted gini drop × number of samples
        self.feature_importance_raw[feat] = \
            self.feature_importance_raw.get(feat, 0.0) + gain * len(y)

        # Build subtrees
        right_idx = [i for i in range(len(y)) if i not in set(left_idx)]
        X_left    = [X[i] for i in left_idx]
        y_left    = [y[i] for i in left_idx]
        X_right   = [X[i] for i in right_idx]
        y_right   = [y[i] for i in right_idx]

        node.label     = None           # internal node — not a leaf
        node.feature   = feat
        node.threshold = thresh
        node.left      = self._build(X_left,  y_left,  depth + 1)
        node.right     = self._build(X_right, y_right, depth + 1)
        return node

    def fit(self, X: list, y: list):
        self.n_total_features       = len(X[0]) if X else 0
        self.feature_importance_raw = {}
        self.root                   = self._build(X, y, 0)
        return self

    def _predict_one(self, node: _DTNode, x: list) -> str:
        if node.label is not None:   # leaf
            return node.label
        if x[node.feature] <= node.threshold:
            return self._predict_one(node.left, x)
        return self._predict_one(node.right, x)

    def predict(self, X: list) -> list:
        return [self._predict_one(self.root, x) for x in X]


class RandomForest:
    """
    Random Forest classifier implemented from scratch.

    VIVA EXPLANATION:
      - Build n_estimators Decision Trees, each on a different bootstrap sample
        (random sample WITH replacement, same size as training data)
      - At each split inside a tree, only consider a random subset of sqrt(n_features)
        features — this de-correlates the trees from each other
      - Final prediction for a new point = majority vote across all trees
      - Feature importance = average weighted Gini drop across all trees,
        normalised to sum to 1

    Why better than a single Decision Tree:
      A single tree memorises the training data (overfits). By averaging many
      trees trained on different subsets, errors cancel out and predictions
      generalise better to new nodes added during simulation.
    """

    def __init__(self, n_estimators: int = 20, max_depth: int = 5,
                 min_samples_split: int = 2, random_state: int = 42):
        self.n_estimators      = n_estimators
        self.max_depth         = max_depth
        self.min_samples_split = min_samples_split
        self.random_state      = random_state
        self.trees             = []
        self.feature_importances_ = []   # normalised importances, one per feature

    def fit(self, X: list, y: list):
        random.seed(self.random_state)
        n          = len(X)
        n_features = len(X[0]) if X else 0
        # sqrt heuristic: number of features to try at each split
        n_feat_split = max(1, int(math.sqrt(n_features)))

        self.trees = []
        # accumulate raw importances per feature across all trees
        accumulated = [0.0] * n_features

        for t in range(self.n_estimators):
            # Bootstrap sample: random with replacement
            indices = [random.randint(0, n - 1) for _ in range(n)]
            X_boot  = [X[i] for i in indices]
            y_boot  = [y[i] for i in indices]

            tree = _DecisionTree(
                max_depth         = self.max_depth,
                min_samples_split = self.min_samples_split,
                n_features_split  = n_feat_split,
            )
            tree.fit(X_boot, y_boot)
            self.trees.append(tree)

            # Accumulate this tree's feature importances
            for feat_idx in range(n_features):
                accumulated[feat_idx] += tree.feature_importance_raw.get(feat_idx, 0.0)

        # Average across trees then normalise so they sum to 1
        avg   = [v / self.n_estimators for v in accumulated]
        total = sum(avg) or 1.0
        self.feature_importances_ = [v / total for v in avg]
        return self

    def predict(self, X: list) -> list:
        """Majority vote across all trees."""
        # Collect predictions from every tree
        all_preds = [tree.predict(X) for tree in self.trees]
        results   = []
        for i in range(len(X)):
            votes = [all_preds[t][i] for t in range(len(self.trees))]
            results.append(Counter(votes).most_common(1)[0][0])
        return results


# ─────────────────────────────────────────────────────────────────
#  TRAIN CLASSIFIER  (now uses scratch RandomForest, no sklearn)
# ─────────────────────────────────────────────────────────────────
def train_classifier(dataset: list):
    """
    Train a Random Forest on the synthetic dataset.
    Returns (trained_model, None, feature_importance_dict).
    scaler is None because features are already in [0,1] range — no scaling needed.

    VIVA EXPLANATION:
      Random Forest builds n_estimators decision trees, each on a bootstrap
      sample of the training data. Each tree considers only sqrt(n_features)
      features at each split. Final prediction is majority vote across all
      trees. Feature importances are the average weighted Gini drop per feature,
      normalised to sum to 1.
    """
    if not dataset:
        return RandomForest(), None, {}

    X = [item[0] for item in dataset]
    y = [item[1] for item in dataset]

    clf = RandomForest(
        n_estimators      = 20,    # 20 trees — sufficient for a small dataset
        max_depth         = 5,     # prevents overfitting on synthetic data
        min_samples_split = 2,
        random_state      = 42,
    )
    clf.fit(X, y)

    feat_names  = ["Population", "Ind.Proximity", "TypeRisk", "Degree"]
    importances = {feat_names[i]: round(float(v), 4)
                   for i, v in enumerate(clf.feature_importances_)}

    return clf, None, importances   # scaler=None throughout


def predict_all(clf, scaler, features: dict) -> dict:
    """
    Run the trained classifier on every active node.
    scaler is always None (features already normalised).
    Returns {node_id: "High"/"Medium"/"Low"}.
    """
    if not features:
        return {}

    node_ids = list(features.keys())
    X        = [features[n] for n in node_ids]

    # scaler is None — no transformation needed
    preds = clf.predict(X)
    return {node_ids[i]: preds[i] for i in range(len(node_ids))}


# ─────────────────────────────────────────────────────────────────
#  PHASE 3 — INTEGRATE INTO SHARED CITY GRAPH
# ─────────────────────────────────────────────────────────────────
def update_city_risk(city, predictions: dict):
    """
    Write risk levels back into the shared CityGraph.

    Multipliers applied to edge["cost"] for each risk level:
        High   (risk_index=0.8) -> effective_cost = base_cost * 1.8
        Medium (risk_index=0.4) -> effective_cost = base_cost * 1.4
        Low    (risk_index=0.1) -> effective_cost = base_cost * 1.1

    Justification for multiplier magnitudes:
        High-risk zones slow emergency vehicles: bystanders crowd streets,
        active incidents may block junctions, and police escort may be needed.
        An 80% overhead (x1.8) reflects this operational friction.
        Medium zones add moderate friction (x1.4). Low zones add a small
        bias (x1.1) so the router naturally prefers safer corridors when
        two paths have equal base cost.

    Integration:
        Both Challenge 3 (ambulance GA / Dijkstra) and Challenge 4 (A* router)
        read edge["cost"] when computing path weights. This function overwrites
        that field directly, so neither module needs to know about risk_index
        separately -- the integration is completely transparent to them.

    base_cost is stored on the first call so that repeated calls (e.g. when
    risk weights shift mid-simulation) never compound the multiplier.
    """
    if not hasattr(city, "risk_index"):
        city.risk_index = {}

    # Step 1: record risk_index on every predicted node
    for nid, label in predictions.items():
        city.risk_index[nid] = RISK_VALUES[label]

    # Step 2: push updated costs into the road edges that ARRIVE at each node.
    # Travel cost is paid on arrival, so we update incoming edges.
    # Ch3 dijkstra_all and Ch4 A* both read edge["cost"] -- overwrite it here.
    if not city.roads:
        return

    for nid, label in predictions.items():
        risk       = city.risk_index.get(nid, 0.0)
        multiplier = 1.0 + risk       # 1.1 for Low, 1.4 for Medium, 1.8 for High

        # Walk every node that has a road pointing TO nid
        for src in city.active_nodes:
            edge = city.roads.get(src, {}).get(nid)
            if edge is None or not isinstance(edge, dict):
                continue
            # Preserve the original road cost on first call -- never compound
            if "base_cost" not in edge:
                edge["base_cost"] = edge.get("cost", 1.0)
            base_cost               = edge["base_cost"]
            edge["cost"]            = round(base_cost * multiplier, 4)
            edge["effective_cost"]  = edge["cost"]
            edge["risk_multiplier"] = multiplier


def deploy_police(predictions: dict, city, num_officers: int = NUM_OFFICERS) -> dict:
    """
    Deploy 10 police officers proportionally by risk level.
    High: 5x weight, Medium: 2x weight, Low: 1x weight.
    Within each level, prioritise nodes by population density.
    """
    high   = [n for n, l in predictions.items() if l == "High"]
    medium = [n for n, l in predictions.items() if l == "Medium"]
    low    = [n for n, l in predictions.items() if l == "Low"]

    total_weight = len(high) * 5 + len(medium) * 2 + len(low) * 1
    if total_weight == 0:
        return {}

    officers_per_high   = (5 / total_weight) * num_officers if high   else 0
    officers_per_medium = (2 / total_weight) * num_officers if medium else 0
    officers_per_low    = (1 / total_weight) * num_officers if low    else 0

    def pop(nid):
        loc = city.assignment.get(nid, "Residential")
        return POP_BY_TYPE.get(loc, 100)

    deployment = {}
    remaining  = num_officers

    for nid in sorted(high, key=pop, reverse=True):
        if remaining <= 0: break
        assigned = min(max(1, round(officers_per_high)), remaining)
        deployment[nid] = assigned
        remaining -= assigned

    for nid in sorted(medium, key=pop, reverse=True):
        if remaining <= 0: break
        assigned = min(max(1, round(officers_per_medium)), remaining)
        deployment[nid] = assigned
        remaining -= assigned

    for nid in sorted(low, key=pop, reverse=True):
        if remaining <= 0: break
        deployment[nid] = 1
        remaining -= 1

    return deployment


# ─────────────────────────────────────────────────────────────────
#  MAIN PIPELINE CONTROLLER
# ─────────────────────────────────────────────────────────────────
class CrimeRiskPipeline:
    """
    Orchestrates the full Challenge 5 pipeline.

    Usage:
        pipeline = CrimeRiskPipeline(city)
        pipeline.run()
        pipeline.predictions       # {nid: "High"/"Medium"/"Low"}
        pipeline.risk_floats       # {nid: 0.1/0.4/0.8}
        pipeline.deployment        # {nid: num_officers}
        pipeline.feature_importance# {feature_name: importance}
        pipeline.cluster_labels    # {nid: "High"/"Medium"/"Low"} from K-Means
    """

    def __init__(self, city, callback=None):
        self.city               = city
        self.callback           = callback
        self.features           = {}
        self.cluster_labels     = {}
        self.predictions        = {}
        self.risk_floats        = {}
        self.deployment         = {}
        self.feature_importance = {}
        self.km                 = None

    def run(self):
        city = self.city
        cb   = self.callback

        if cb: cb("Extracting node features...")
        self.features = extract_features(city)

        if not self.features:
            if cb: cb("ERROR: No active nodes found.")
            return

        # ── Phase 1: K-Means Clustering ──────────────────────────
        if cb: cb("Phase 1: K-Means clustering (K=3, unsupervised)...")
        self.km = KMeans(k=NUM_CLUSTERS, max_iter=100, n_init=5)
        self.km.fit(self.features)
        self.cluster_labels = label_clusters(self.km, self.features)

        # ── Generate Synthetic Dataset ────────────────────────────
        if cb: cb("Generating synthetic crime dataset...")
        dataset = generate_synthetic_dataset(city, self.features, self.cluster_labels)

        # ── Phase 2: Train Random Forest (from scratch) ───────────
        if cb: cb("Phase 2: Training Random Forest (20 trees, from scratch)...")
        clf, scaler, self.feature_importance = train_classifier(dataset)

        # ── Predict Risk for All Nodes ────────────────────────────
        if cb: cb("Predicting crime risk for all nodes...")
        self.predictions = predict_all(clf, scaler, self.features)

        # ── Phase 3: Update Shared City Graph ─────────────────────
        if cb: cb("Phase 3: Updating shared CityGraph risk_index values...")
        update_city_risk(city, self.predictions)
        self.risk_floats = {nid: RISK_VALUES[lbl]
                            for nid, lbl in self.predictions.items()}

        # ── Deploy Police Officers ────────────────────────────────
        if cb: cb("Deploying police officers by risk level...")
        self.deployment = deploy_police(self.predictions, city)

        # ── Summary ───────────────────────────────────────────────
        counts = {"High": 0, "Medium": 0, "Low": 0}
        for lbl in self.predictions.values():
            counts[lbl] = counts.get(lbl, 0) + 1

        if cb:
            cb(f"Done. High={counts['High']} Medium={counts['Medium']} "
               f"Low={counts['Low']} nodes.")
            if self.feature_importance:
                cb(f"Feature importances: {self.feature_importance}")

        return self


# ─────────────────────────────────────────────────────────────────
#  Standalone entry point (imported by GUI)
# ─────────────────────────────────────────────────────────────────
def run_challenge5(city, callback=None):
    pipeline = CrimeRiskPipeline(city, callback=callback)
    pipeline.run()
    return pipeline


# ─────────────────────────────────────────────────────────────────
#  Standalone demo
# ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys, os, io
    sys.path.insert(0, os.path.dirname(__file__))
    from challenge1 import CityLayoutManager
    from contextlib import redirect_stdout

    print("Building city...")
    tc  = {"Residential": 6, "Hospital": 2, "School": 2,
           "Industrial": 2, "PowerPlant": 2, "AmbulanceDepot": 1}
    mgr = CityLayoutManager()
    buf = io.StringIO()
    with redirect_stdout(buf):
        mgr.initialize(5, 5, sum(tc.values()), tc, 300, 500)

    print("Running Challenge 5 pipeline (scratch Random Forest)...")
    def cb(msg): print(" ", msg)
    pipeline = run_challenge5(mgr.city, callback=cb)

    print("\nPredictions (first 8 nodes):")
    for nid, lbl in list(pipeline.predictions.items())[:8]:
        coords = mgr.city.coords(nid)
        loc    = mgr.city.assignment.get(nid)
        risk   = mgr.city.risk_index.get(nid, 0.0)
        print(f"  {coords} [{loc}] -> {lbl} (risk_index={risk})")

    print(f"\nPolice deployment ({NUM_OFFICERS} officers):")
    for nid, n in pipeline.deployment.items():
        print(f"  {mgr.city.coords(nid)} [{mgr.city.assignment.get(nid)}]: {n} officer(s)")

    print(f"\nFeature importances: {pipeline.feature_importance}")