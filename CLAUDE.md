# CLAUDE.md — MLB DFS Research & Optimization Engine

## Project Mission

Build an MLB DFS research, ownership, projection, and lineup optimization engine that identifies profitable DFS opportunities through data analysis, specialist AI agents, ownership analysis, and mathematical optimization.

The immediate priority is NOT building a polished SaaS application.

The immediate priority is getting a working research engine running as quickly as possible so its recommendations can be tested against real MLB slates and actual DFS results.

## Core Philosophy

Build → Run → Record → Evaluate → Improve.

Avoid unnecessary architecture.

Do not build features merely because they may be useful later.

Every major feature should directly help:

1. Produce DFS projections
2. Identify strong plays
3. Identify sleepers
4. Estimate ownership
5. Identify leverage
6. Generate optimized lineups
7. Evaluate predictions against actual results
8. Improve future predictions

## Initial Sport

MLB only.

Do not add NFL, NBA, NHL, PGA, or other sports until explicitly requested.

## Initial DFS Objective

Focus on tournament/GPP lineup construction and identifying leverage against the field.

The system should eventually support cash contests, but GPP research is the initial priority.

## System Architecture

Use a Head Agent with specialized research agents.

### DFS Director / Head Agent

The Head Agent coordinates all specialist agents.

Responsibilities:

* Request specialist analysis
* Combine specialist outputs
* Resolve conflicting signals
* Rank players
* Rank pitchers
* Rank stacks
* Identify sleepers
* Identify fades
* Identify leverage plays
* Create the recommended DFS player pool
* Send structured player data to the optimizer

The Head Agent should not duplicate work performed by specialist agents.

### Pitcher Agent

Analyze starting pitchers using:

* Strikeout rate
* Walk rate
* K-BB%
* FIP
* xFIP
* SIERA when available
* ERA/xERA
* xwOBA
* CSW
* Swinging-strike rate
* Velocity
* Velocity changes
* Pitch mix
* Pitch-mix changes
* Spin
* Hard-hit rate
* Barrel rate
* Ground-ball rate
* Platoon splits
* Opponent strikeout tendencies
* Opponent offensive quality
* Stadium
* Weather
* Umpire
* Expected workload
* Salary

Return projection, ceiling, floor, risk, confidence, matchup score, and supporting reasons.

### Batter Agent

Analyze hitters using:

* wOBA
* xwOBA
* ISO
* xSLG
* Exit velocity
* Barrel rate
* Hard-hit rate
* Launch angle
* Bat speed when available
* Platoon splits
* Pitch-type performance
* Opposing pitcher pitch mix
* Batting order
* Stadium
* Weather
* Opposing bullpen
* Salary
* Recent underlying Statcast changes

The Batter Agent should actively look for players whose underlying metrics are improving before their traditional statistics reflect the improvement.

Return projection, ceiling, floor, matchup score, value score, risk, confidence, and supporting reasons.

### Game Environment Agent

Analyze each game using:

* Weather
* Temperature
* Wind
* Wind direction
* Humidity
* Rain risk
* Stadium
* Roof status
* Park factors
* Vegas game total when available
* Team implied totals
* Bullpen strength
* Bullpen fatigue

Return:

* Hitting environment score
* Pitching environment score
* Stack score
* Weather adjustment
* Risk level

### Umpire Agent

Analyze umpire tendencies when data is available.

Consider:

* Strike zone tendencies
* Called strikes
* Walk tendencies
* Strikeout tendencies
* Run environment
* Pitcher friendliness
* Hitter friendliness

Umpire data should adjust projections but should not dominate them.

### Ownership Agent

Estimate:

* Player ownership
* Pitcher ownership
* Stack ownership
* Chalk level
* Contrarian value
* Optimal lineup appearance
* Leverage
* Potential lineup duplication

Ownership estimates must include a confidence value.

Do not present uncertain ownership estimates as known facts.

## Data Sources

Prefer reliable structured sources.

Initial priorities:

* MLB / MLB Stats
* Baseball Savant / Statcast
* DFS salary CSV files
* Weather data
* Stadium data

Additional data providers may be added later.

Raw source data should be preserved whenever practical so research can be reproduced.

## Structured Agent Outputs

Agents should return structured data.

Do not rely solely on prose responses.

Use typed schemas for outputs.

Example player analysis:

{
"player_id": "",
"player_name": "",
"projection": 0,
"ceiling": 0,
"floor": 0,
"value_score": 0,
"ownership_projection": 0,
"leverage_score": 0,
"risk_score": 0,
"confidence": 0,
"tags": [],
"reasons": []
}

## Optimizer

The lineup optimizer is NOT an LLM agent.

Use deterministic mathematical optimization.

The optimizer will eventually support:

* Salary cap
* Roster positions
* Player locks
* Player exclusions
* Minimum exposure
* Maximum exposure
* Team stacks
* Stack rules
* Unique player requirements
* Maximum lineup ownership
* Minimum projection
* Minimum ceiling
* Leverage constraints
* Multiple lineup generation

AI agents recommend and evaluate players.

The mathematical optimizer constructs valid lineups.

Keep those responsibilities separate.

## Evaluation System

Evaluation is a first-class part of the product.

Every slate should eventually preserve:

* Pregame projection
* Pregame ownership estimate
* Pregame agent rankings
* Pregame confidence
* Pregame recommended plays
* Pregame fades
* Pregame stacks
* Generated lineups
* Actual fantasy points
* Actual ownership when available
* Winning lineups when available
* Contest results when available

Never overwrite pregame predictions with postgame information.

The system must make it possible to determine what the agents knew at the time of the prediction.

## Prevent Lookahead Bias

Historical testing must only use information that would have been available before slate lock.

Never allow future information to influence historical predictions.

## Development Priorities

Priority 1:
Get one MLB slate successfully loaded.

Priority 2:
Analyze pitchers.

Priority 3:
Analyze hitters.

Priority 4:
Analyze game environment.

Priority 5:
Combine analysis through the DFS Director.

Priority 6:
Produce a ranked DFS player pool.

Priority 7:
Add basic ownership estimates.

Priority 8:
Generate valid optimized lineups.

Priority 9:
Save predictions.

Priority 10:
Compare predictions with actual results.

Only after this loop works reliably should significant UI development begin.

## Development Rules

Prefer simple code over premature abstraction.

Do not create microservices.

Do not introduce infrastructure unless required.

Do not create unnecessary interfaces or abstraction layers.

Do not rewrite working components without a measurable reason.

Keep functions small and testable.

Use structured logging.

Fail loudly when critical DFS data is missing.

Never silently invent missing statistics.

Record the source and timestamp of important data whenever practical.

Add tests for calculation and optimizer logic.

## AI Rules

AI should interpret data, identify relationships, produce research explanations, and assist decision making.

AI should NOT invent statistics.

Calculated values should be produced programmatically whenever possible.

LLMs should receive relevant structured statistics rather than being expected to retrieve or remember them.

Every agent should distinguish between:

* Observed data
* Calculated metrics
* Model predictions
* AI interpretation

## Current Definition of Success

The initial system is successful when:

1. A current MLB slate can be loaded.
2. Pitchers can be analyzed.
3. Hitters can be analyzed.
4. Game conditions can be analyzed.
5. Specialist reports reach the DFS Director.
6. The Director produces ranked plays, fades, sleepers, pitchers, and stacks.
7. The system produces DFS projections and ownership estimates.
8. Valid DFS lineups can be generated.
9. Pregame predictions can be saved.
10. Predictions can later be compared with actual results.

Optimize for reaching this feedback loop quickly.

## Important Instruction to Claude Code

Before adding substantial architecture, dependencies, databases, queues, services, or frameworks, determine whether the feature is necessary for the current working milestone.

When a simpler implementation will allow us to test the DFS hypothesis sooner, choose the simpler implementation.

The primary goal is learning from real DFS results, not demonstrating software architecture.
