  - Fuel logistics for furnaces and smelters                                                                                                                            20:26:02 [128/40992]
  - Water power transmission via axles and gears
  - Wind power grids
  - Mechanical clutch, gearbox, and power switching systems
  - Pump stacks for irrigation, drainage, and pressure systems
  - Pipe or channel networks for fluids
  - Floodgates, sluices, and reservoir management
  - Pressure logic for traps and defenses
  - Automated bridge raising on alerts
  - Sensor systems: motion, pressure plate, tripwire, water level
  - Signal logic using levers and link networks
  - Programmable logic chains for fortress automation
  - Workshop job macros and production presets
  - Conditional production rules based on stock levels
  - Automatic tool replacement and maintenance orders
  - Equipment loadout automation for squads
  - Uniform distribution depots
  - Ammunition supply chains
  - Hospital supply automation
  - Kitchen and tavern provisioning routes
  - Farming irrigation automation
  - Seed and fertilizer distribution loops
  - Livestock feeding and pen supply logistics
  - Butchery and tallow processing chains
  - Waste removal and refuse routing
  - Ash, slag, and tailings disposal systems
  - Dangerous-material handling zones
  - Recycling and salvage workshops
  - Demolition and deconstruction recovery routing
  - Building-material staging zones
  - Construction crew assignment and batching
  - Blueprint-driven auto-build sequences
  - Housing assignment automation
  - Bed, food, and clothing entitlement rules
  - Immigration intake and starter-kit distribution
  - Trade packing, caravan loading, and customs depots
  - Import/export contracts and recurring shipments
  - Price-aware trade automation
  - Fortress-wide resource dashboards
  - Throughput and bottleneck heatmaps
  - Path congestion analysis tools
  - Power network visualization
  - Fluid flow visualization
  - Logistics replay and debug timeline
  - Remote outposts linked by supply lines
  - Messenger/post system for distant job dispatch
  - Seasonal logistics planning
  - Weather-resistant infrastructure upgrades
  - Conveyor belts for workshop-to-stockpile automation
  - Mechanical rollers for directional item movement
  - Minecart rail networks with loading/unloading stops
  - Hauling depots and transfer stations
  - Route templates and reusable logistics blueprints
  - Priority lanes for military, hauling, or emergency traffic
  - One-way road and corridor designations
  - Traffic lights, gates, or signal-controlled intersections
  - Bridge networks and raised causeways
  - Tunnel boring and underground freight corridors
  - Elevator or lift platforms for multi-z cargo movement
  - Winches, cranes, and hoists for heavy materials
  - Vertical shafts with bucket-chain hauling
  - Port and dock logistics for river/coastal maps
  - Warehouses with capacity classes and overflow routing
  - Central distribution hubs
  - Input/output buffers for every workshop
  - Pull-based logistics requests from workshops
  - Push-based logistics rules from stockpiles
  - Standing orders for auto-haul and auto-refill
  - Refill thresholds for critical goods
  - Emergency reserve stockpiles
  - Quarantine stockpiles for dangerous or spoiled goods
  - Cold storage and preservation rooms




more milestones

  44) WALL CONSTRUCTION SYSTEM
    * Add a dedicated wall build mode that lets the player place planned wall segments on valid floor or ground tiles using click, drag, and line placement.
    * Wall placements must create authoritative construction jobs on the server rather than instantly mutating terrain on the client.
    * Each wall tile must have at least four states: `planned`, `materials reserved`, `under construction`, and `finished`.
    * Finished walls must become solid blocking terrain for movement, line of sight, room enclosure, and later combat cover calculations.
    * The player must be able to choose wall material classes such as rough stone block, cut stone block, wood, or packed earth, with each material defining appearance, durability, and
  build cost.
    * Invalid wall placements must be rejected with explicit reasons such as `occupied tile`, `blocked by stockpile`, `invalid support`, `reserved by another job`, or `cannot build in open
  air`.

  45) WALL JOB FLOW AND MATERIAL HANDLING
    * Placing a wall must generate one or more construction jobs that reserve a build site, required materials, and a hauling path from source stockpiles or nearby loose items.
    * Haulers must move required materials to the wall site before builders can begin construction.
    * Builders must spend time at the wall site to complete the build, with construction duration based on material class, worker skill, and tool availability.
    * If materials are missing, the wall job must remain visible as `blocked` and surface the exact missing input in the UI.
    * Cancelling an unstarted wall must release reserved materials, and cancelling an in-progress wall must define whether partial materials are recoverable or lost.
    * Wall construction order must be deterministic so multiplayer players and reconnecting clients observe the same sequence and progress.

  46) WALL SHAPES, CONNECTIONS, AND STRUCTURAL RULES
    * Adjacent wall segments must auto-connect visually into straight runs, corners, junctions, and enclosed rooms without manual sprite selection.
    * Walls must support at least single-tile placement, drag-line placement, and rectangular perimeter placement.
    * Walls must integrate with doors, gates, windows, stairs, and ramps as future adjacent structure types without requiring a redesign of the wall tile model.
    * Deconstructing a wall must create an authoritative teardown job instead of instant deletion, and the teardown must respect support and access rules.
    * The UI must show wall health and material

  47) TUNNEL DESIGNATION SYSTEM
    * Add a tunneling mode that lets the player designate contiguous digging paths or rectangular dig regions through solid terrain.
    * Tunnel designations must create authoritative dig jobs on the server and visually mark targeted tiles in the client before excavation is complete.
    * The player must be able to issue at least `dig tunnel`, `dig room`, and `cancel dig` actions through the keyboard-first task palette and direct cursor interaction.
    * Tunnel jobs must remain queued until a valid miner, path, and tool are available, and the UI must show queued, assigned, blocked, and complete states.
    * Digging through terrain must convert solid tiles into walkable tunnel floor tiles and produce excavated materials such as stone, ore, or special underground resources.
    * Tunnel designations must support multi-tile drag placement so the player can carve long corridors efficiently.

  48) TUNNEL EXCAVATION RULES
    * Only diggable terrain classes such as soil, stone, ore, and other defined subterranean materials may be designated for tunneling.
    * Each diggable material must define hardness, excavation time, drop table, and optional hazard properties.
    * Miners must move adjacent to or onto a valid work position for the target tile before excavation progresses.
    * Excavation must proceed tile by tile in deterministic order and must visibly update the map as tiles are completed.
    * If a designated tile becomes unreachable or unsafe, the job must enter a blocked state rather than silently disappearing.
    * Completed tunnels must immediately affect pathfinding, visibility, room detection, hauling routes, and later enemy approach logic.

  49) WALLS, TUNNELS, AND ROOM FORMATION
    * Built walls and excavated tunnels must participate in the same enclosure and room-detection system so players can form underground rooms by carving space and sealing it with walls.
    * A tunnel network that opens into a constructed wall perimeter must be recognized as a continuous interior space when fully enclosed.
    * The room system must be able to distinguish `outdoor`, `dug interior`, `constructed interior`, and `breached` states based on current wall and tunnel geometry.
    * Breaching a wall into open air or into hostile caverns must immediately update room safety, shelter scoring, and path availability.
    * The player must be able to inspect a tile and understand whether it is part of a room, corridor, unfinished dig, or construction boundary.
    * This makes walls and tunnels foundational to shelter, logistics, defense, and workshop placement.

  50) UI FOR WALLS AND TUNNELING
    * Add separate searchable task/build entries for `Wall`, `Dig Tunnel`, `Dig Room`, `Cancel Dig`, and `Deconstruct Wall`.
    * Entering wall or tunneling mode must change the cursor, show a ghost preview or dig overlay, and display material requirements or dig target info in the bottom panel.
    * Selected planned walls and dig designations must show current job state, assigned dwarf, reserved materials or tools, and blocked reasons.
    * The player must be able to drag out long wall runs and tunnel runs, with live previews of the exact affected tiles before confirming.
    * The client must render planned walls, active construction, planned digs, and active excavation with distinct visual states so the player can read the fortress at a glance.
    * The event log should record important construction and tunneling events such as job queued, completed corridor, room opened, breach detected, and collapse warning.

  51) LOGISTICS AND ENGINEERING INTEGRATION
    * Wall construction must consume materials from stockpiles using the logistics rule system, including pull requests for active construction zones and push rules from masonry workshops.
    * Tunneling must output excavated materials onto the ground or into nearby designated collection zones, creating follow-up hauling jobs automatically.
    * Construction staging zones may optionally request blocks, wood, or tools in advance so large wall projects do not stall one tile at a time.
    * Tunnel spoil and mined ore should be eligible for stockpile push rules so excavation feeds directly into fortress industry.
    * Walls can serve as controlled barriers for logistics flow, forcing roads, tunnels, and hauling corridors into predictable routes.
    * This ties building mechanics directly into stockpiles, workshops, hauling, and fortress planning instead of isolating them as cosmetic systems.
