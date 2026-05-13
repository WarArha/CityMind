# CityMind
AI-powered smart city simulation using CSP, Kruskal MST, Genetic Algorithm, A* routing, K-Means, and Random Forest with a Pygame GUI, crime-risk heatmap, ambulance coverage, road optimization, and 20-step live integration simulation.


# CityMind: An Urban Intelligence System

CityMind is an AI-based urban intelligence simulation system designed to help city authorities make smarter decisions for planning, emergency response, ambulance placement, road design, and crime-risk prediction.

The city is represented as a shared grid-based graph. Each location is a node, and roads are edges. All modules operate on the same city graph, so any change in one module is immediately visible to the rest of the system.

---

## Project Overview

The project solves five major AI challenges:

1. City Layout Planning
2. Road Network Optimization
3. Ambulance Placement
4. Emergency Routing Under Changing Conditions
5. Crime Risk Prediction and Integration

A graphical interface is included to visualize the city, roads, ambulances, emergency routes, crime-risk heatmap, and live simulation events.

---

## Features

- Grid-based city graph representation
- Constraint-based city layout generation
- Road network optimization with backup route safety
- Genetic Algorithm based ambulance placement
- A* emergency routing with real-time rerouting
- K-Means clustering for neighborhood grouping
- Random Forest classification for crime-risk prediction
- Police deployment based on predicted risk
- Crime-risk heatmap overlay
- Ambulance coverage overlay
- Road network and blocked road visualization
- 20-step integrated simulation
- Live event log
- Interactive Pygame dashboard GUI

---

## Technologies Used

- Python
- Pygame
- Graph algorithms
- Constraint Satisfaction Problem techniques
- Genetic Algorithm
- A* Search
- Dijkstra’s Algorithm
- Kruskal’s Minimum Spanning Tree
- K-Means Clustering
- Random Forest Classification

---

## Challenge 1: City Layout Planning

The city layout is solved as a Constraint Satisfaction Problem.

### Techniques Used

- Backtracking
- MRV, Minimum Remaining Values
- Forward Checking
- Min-Conflicts fallback
- BFS for hop-distance validation

### Rules Checked

- Industrial zones cannot be adjacent to schools or hospitals.
- Every residential area must be within 3 hops of at least one hospital.
- Every power plant must be within 2 hops of at least one industrial zone.
- If no valid layout is found, the system reports the conflicting rule and proposes a minimum-conflict solution.

---

## Challenge 2: Road Network Optimization

Roads are built after the city layout is generated.

### Techniques Used

- Kruskal’s Minimum Spanning Tree
- Union-Find
- Dijkstra-based second-path augmentation

### Purpose

The system connects all active locations using minimum total road cost. It also ensures that the Primary Hospital and Ambulance Depot have an alternate backup route if a road fails.

---

## Challenge 3: Ambulance Placement

The city has three ambulances that must be placed to reduce worst-case response time.

### Technique Used

- Genetic Algorithm

### GA Components

- Chromosome: three ambulance node positions
- Fitness: negative worst-case distance from any node to nearest ambulance
- Selection: tournament selection
- Crossover: single-point crossover
- Mutation: random ambulance relocation
- Elitism: best solutions carried forward
- Optimization: precomputed distance matrix using Dijkstra

---

## Challenge 4: Emergency Routing

Emergency teams must reach trapped civilians while roads may become blocked.

### Technique Used

- A* Search

### Features

- Uses Manhattan distance heuristic
- Avoids blocked roads
- Recalculates route when flooding occurs
- Finds the shortest currently available path
- Skips unreachable civilians and continues to reachable ones

---

## Challenge 5: Crime Risk Prediction

Crime-risk prediction is handled using a machine-learning pipeline.

### Techniques Used

- K-Means Clustering
- Synthetic crime dataset generation
- Random Forest Classification

### Features Used

Each city node is represented using:

- Normalized population
- Industrial proximity
- Type-based risk
- Degree/connectivity

The final predicted risk is written back into the shared city graph as `risk_index`.

Risk levels:

- Low
- Medium
- High

High-risk locations increase effective travel cost for routing and ambulance placement.

---

## System Integration Simulation

The system includes a 20-step simulation that connects all modules.

During simulation:

- The city layout is used as the initial grid.
- The road network defines travel paths.
- Crime-risk predictions update graph weights.
- Ambulance placements are re-evaluated.
- Flooding events randomly block roads.
- A* reroutes emergency paths in real time.
- The GUI event log records every important action.

The simulation can be run step-by-step or in slow automatic mode.

---

## GUI Features

The Pygame interface includes:

- City overview
- Road network overlay
- Ambulance coverage overlay
- Emergency route overlay
- Crime-risk heatmap
- Live event log
- Simulation controls
- Scrollable control panels
- Responsive dashboard layout

---

## How to Run

Make sure Python is installed.

Install Pygame if needed:

```bash
pip install pygame
