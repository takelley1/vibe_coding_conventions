You are Codex acting as a senior staff engineer and tech lead. Build a polished multiplayer Dwarf Fortress - like game using the current repo as a starting point.
Reference `README.md` and `DESIGN.md` to understand the current vision for the game and where it currently is.

Core goals

* This must be impressive to non-engineers in a live demo (multiplayer, singleplayer, shared server accessed over a web client, deterministic long-running simulation, many interconnected systems)
* This must also be impressive to engineers (clean architecture, strong types, tests, fully-tested code, bug-free code, easy to read and understand, performant).
* You will run for hours: plan first, then implement milestone by milestone. Do not skip the planning phase.
* Ask any necessary questions while in plan mode so I can respond to them before you kick off. Remember, after we get the plan and you exit plan mode, you cannot return control to me until everything is fully implemented. Plan mode is the only time you will be able to ask me questions.

Hard requirements

* Local run experience: one command to start (document exact commands). Must run on macOS with Rust and TypeScript
* Tech stack: Reference `README.md` and `DESIGN.md`. Use only open source dependencies.
* Runs fully locally: no external hosted services.
* Every milestone must include verification steps (tests, lint, typecheck, deterministic snapshots).
* Ignore the `specs/` dir

Deliverable
A repo that contains:

* A working implementing the features below
* A short architecture doc explaining the data model, rendering pipeline, server and client implementation, client sync behavior to the server, and how many objects are all updated in parallel
* Scripts: dev, build, test, lint, typecheck, export
* A `Documentation.md` file capturing the full implementation plan and ongoing notes
* You do not need to complete the below spec in order. Rather it's up to you to determine dependency ordering for features.

Product spec (build this)

  1) AUTHORITATIVE PLAYABLE CLIENT SHELL
    * Replace the current debug-style DOM HUD with a native canvas-rendered HUD layer; keep DOM limited to bootstrap/root mounting and render all persistent game chrome inside the game
  client.
    * Reserve a top bar at roughly 5% of screen height for fortress name, connection state, server tick, game clock, and calendar, all driven by authoritative replicated server state.
    * Reserve a bottom panel at roughly 20% of screen height for selected-unit details, world summary, alerts, and contextual action help; if nothing is selected, show fortress-wide status
  instead of an empty panel.
    * Ship a consistent 16-bit stone/clay/slab visual language using browns, greys, tans, black, and off-white, with atlas-backed panel frames, icons, and portrait frames rather than CSS-
  only styling.

  2) DWARF INSPECTOR AND PORTRAITS
    * Extend replicated citizen state to include portrait seed, age, race, ethnicity, birth date, marital status, current task, likes/dislikes, health summary, labor roles, and squad
  membership.
    * Show the selected dwarf’s portrait, full identity block, current location, current job, and health state in the bottom panel, and update it live from server ticks.
    * Add explicit status fields for idle, mining, hauling, crafting, wounded, hungry, exhausted, and drafted so the UI reflects real authoritative simulation states.
    * When multiple dwarves are selected, replace the single-dwarf layout with a group summary showing count, average health, shared tasks, and bulk-order actions.

  3) KEYBOARD-FIRST COMMAND MODE
    * Pressing `T` opens a native task palette overlay that lists task families and hotkeys; the overlay must not pause the sim and must close cleanly with `Esc`.
    * Two-key or three-key chords enter command modes, for example `TM` mining, `TZS` stockpile, `TZW` workshop, (task T - zone Z - workshop W) `TB` build, and `TC` cancel designation.
    * Entering a command mode changes the cursor icon, the bottom-panel help text, and the input routing rules until the command is completed or cancelled.
    * Every accepted or rejected command must surface authoritative feedback in the event log and rejection banner instead of relying on client-only optimistic state.

  4) MINING DESIGNATIONS AND JOB QUEUE
    * Replace the current single-tile mine interaction with click-drag rectangular mining designations that create authoritative queued jobs per tile.
    * Track each mining job through `queued`, `assigned`, `in_progress`, `blocked`, `cancelled`, and `complete` states and replicate those states to the client.
    * Idle dwarves with mining labor enabled claim nearby mining jobs, path to them, dig them, and expose visible progress/task feedback in the UI.
    * Mining solid tiles must drop stone or ore items onto the world so the result of mining feeds later hauling and crafting loops.

  5) STOCKPILES AND HAULING
    * `TZS` enters stockpile paint mode; dragging over floor tiles creates a stockpile zone, colors those tiles in the viewport, and creates an authoritative stockpile record with capacity
  and filters.
    * Support stockpile filters by item class and quality, using the existing stockpile filter data surfaces as the starting point for a real playable stockpile UI.
    * Loose materials on the ground become haul jobs; idle dwarves with hauling labor move items from world tiles into matching stockpile tiles.
    * Build and workshop jobs must reserve materials from stockpiles first, and the UI must show blocked reasons like no path, no free tile, wrong filter, or reserved item.

  6) WORKSHOPS, TOOLS, AND CRAFTING TREE
    * `TZW` enters workshop zone mode; dragging creates a workshop footprint and lets the player choose a type such as carpenter, mason, smelter, or generic craft bench.
    * Add an early production chain where dwarves gather wood or mine ore/stone, craft basic tools first, then craft finished goods like doors and beds.
    * Make workshop jobs authoritative queue entries with recipe id, quantity, ingredient reservations, progress, output location, and completion events.
    * Add a dedicated crafting-tree screen that shows unlocked recipes, prerequisites, required workshop type, and missing materials.

  7) BUILD ORDERS AND PLACEABLE STRUCTURES
    * `TB` enters build mode and lets the player place structures such as doors, beds, walls, and benches using crafted materials.
    * Placement previews must validate terrain, occupancy, and reserved materials before a build order is accepted by the server.
    * Accepted build orders create construction jobs that pull materials from stockpiles, wait for a qualified dwarf, and transition from ghost preview to finished structure.
    * Doors and beds must have gameplay effects, with doors affecting path access and beds satisfying rest/sleep needs.

  8) WORLD GENERATION AND FORTRESS CREATION
    * Add a fortress-creation flow before join where the player sets fortress name, password, seed, embark location, and worldgen parameters.
    * Replace the current simple layered world with deterministic worldgen that produces surface biomes, mountains, grasslands, trees, deserts, ore strata, caves, and 1024 z-level depth.
    * Expose worldgen parameters for biome weights, mountain density, vegetation density, ore richness, and water frequency, with presets plus manual overrides.
    * Spawn an initial embark zone, starting dwarves, and starter resources so a newly generated world is immediately playable.

  9) DAY/NIGHT CYCLE, CLOCK, AND CALENDAR
    * Add an authoritative game clock where one full day lasts about 30 real minutes, mapped deterministically from server ticks.
    * Replicate current hour, day, month, season, and daylight phase to the client and display them in the top HUD bar.
    * Shift world lighting, sky palette, and ambient colors across dawn, day, dusk, and night without making time progression client-authoritative.
    * Use this clock as the scheduler for enemy spawning, sleep windows, workshop shifts, and later seasonal systems.

  10) NIGHT ENEMIES AND FORTRESS DEFENSE
    * Spawn hostile creatures at night from biome-appropriate tables, with an initial set of zombies, elves, bears, and wolves.
    * Enemies must path toward fortress entrances, attack dwarves or structures they encounter, and remain fully server-authoritative.
    * At sunrise, undead burn and die while living nighttime raiders retreat or despawn according to species rules, with visible world and event-log feedback.
    * Add the first real defense loop with draftable squads, station/attack/retreat orders, combat alerts, health display, and casualty reporting.

  11) MULTIPLAYER FORTRESS SESSIONS
    * Expand the current one-fortress-per-server model into a many-fortress-per-server tenancy layer without changing the Rust authoritative architecture.
    * The entry flow must support create fortress, join fortress, and reconnect using fortress name plus password.
    * Each fortress instance needs isolated simulation state, player roster, persistence artifacts, and tick/metrics accounting.
    * The client should show which other players are in the same fortress and surface shared-presence cues like recent orders or active selections.

  12) ISOMETRIC 3/4 RENDERER CONVERSION
    * Replace the current top-down projection with a 3/4 isometric projection while keeping the authoritative server grid and simulation coordinates unchanged.
    * Update terrain, settlers, structures, cursors, drag-selection, and designation overlays so hit testing matches the isometric sprites in screen space.
    * Add depth sorting and cutaway rules so walls, floors, and neighboring z-levels remain readable during mining, hauling, and combat.
    * Preserve existing camera pan, zoom, z-level stepping, and selection behavior after the projection change, with new acceptance tests for click accuracy.

  13) VERTICAL-SLICE FLESH-OUT IDEAS
    * Add hunger, sleep, shelter, and morale so beds, stockpiles, food, and defended rooms matter early.
    * Add a fortress event log and alert stack for arrivals, attacks, injuries, crafted items, completed jobs, and rejected commands.
    * Add save/load for fortress instances so created worlds and multiplayer sessions survive server restarts.

  14) NEEDS SIMULATION: HUNGER, SLEEP, SHELTER, AND MORALE
    * Add four authoritative per-dwarf need meters: `hunger`, `fatigue`, `shelter`, and `morale`, each updated every server tick and replicated to clients.
    * Define deterministic thresholds for each meter: `stable`, `warning`, `critical`, and `broken`, and require the client to show the current threshold state in the dwarf inspector and
  roster.
    * Hunger must rise over time and be reduced only when a dwarf consumes food from a valid food stockpile or meal source; if no food is reachable, the dwarf enters a `hungry` then
  `starving` state with explicit morale penalties.
    * Fatigue must rise while awake and fall only when the dwarf occupies a valid bed; if no bed is available, the dwarf sleeps on the floor with reduced recovery and a morale penalty.
    * The game must clearly show when a dwarf is sleeping by showing "Zzzz" coming from him/her
    * Shelter must be computed from the room or zone the dwarf occupies, using simple early rules: indoors, enclosed, bed nearby, and hostile-free; uncovered outdoor sleeping or idling at
  night reduces shelter.
    * Morale must be a derived authoritative stat affected by hunger, fatigue, injuries, shelter quality, nearby death, combat danger, and recent successful work completion.
    * When a need reaches `critical`, the dwarf must autonomously reprioritize toward a valid recovery action such as eating, finding a bed, or retreating to shelter, unless drafted or
  otherwise hard-locked by higher-priority orders.
    * Expose need-driven blocked states in the UI, such as `No food reachable`, `No bed assigned`, `Unsafe shelter`, or `Morale break`, so the player can diagnose fortress problems without
  inspecting logs.
    * Beds, food stockpiles, and enclosed defended rooms must therefore become mechanically useful in the earliest playable loop rather than decorative.

  15) FOOD, REST, AND BED ASSIGNMENT LOOP
    * Add a minimal early food item class, such as `raw food` and `meal`, with stockpile compatibility and simple consumption rules.
    * Add a `bed assignment` system where a placed bed can be unassigned or assigned to a specific dwarf, and show the current bed assignment in the dwarf inspector.
    * Add a `sleep job` that reserves an assigned bed or nearest free bed and moves the dwarf to it when fatigue crosses the sleep threshold.
    * Add a `consume food job` that reserves a reachable food item and moves the dwarf to a valid eating location when hunger crosses the eating threshold.
    * Reject bed placement or assignment commands when the target tile is invalid, occupied, or not fully built, and surface the rejection reason in the UI and event log.
    * Require the UI to show each dwarf’s current recovery target, for example `Going to bed`, `Looking for food`, or `Cannot find shelter`.

  16) DEFENDED ROOMS AND EARLY SHELTER SCORING
    * Add a simple room-detection pass that marks contiguous enclosed floor areas as rooms when they are surrounded by walls and connected by doors or open walkable tiles.
    * Compute an early shelter score for each room based on enclosure, number of beds, light/day exposure, nearby stockpiles, and presence of hostile units within a danger radius.
    * Replicate the shelter score and room type to the client so the bottom panel can show whether a selected dwarf is in `Unsafe outdoors`, `Rough shelter`, or `Secure room`.
    * Add an early `safe room` designation or inferred fallback shelter so dwarves under nighttime threat have a deterministic retreat destination.
    * Make nighttime enemy pressure interact directly with shelter and morale so defended sleeping quarters matter before deeper economy systems exist.

  17) FORTRESS EVENT LOG
    * Add an authoritative event stream on the server with typed event categories such as `arrival`, `attack`, `injury`, `craft_complete`, `job_complete`, `job_blocked`,
  `command_rejected`, `night_started`, and `sunrise`.
    * Every emitted event must include tick, event type, fortress id, involved entity ids if any, severity, and a ready-to-render player-facing message.
    * Replicate recent events to all connected clients for the same fortress and append them to a scrollable event log panel in the client UI.
    * Keep event ordering stable and deterministic across reconnects by using authoritative sequence ids rather than client-local append order.
    * Add filters for `all`, `combat`, `economy`, `needs`, and `system` so players can inspect the relevant stream without losing raw data.
    * Persist enough recent event history that reconnecting players can see what happened while disconnected.

  18) ALERT STACK AND PRIORITY BANNERS
    * Add a separate authoritative alert system for high-priority conditions that require immediate player awareness, distinct from the full event log.
    * Alert types must include `hostiles detected`, `dwarf starving`, `dwarf collapsing from exhaustion`, `bed missing`, `food shortage`, `craft complete`, `save failed`, and `command
  rejected`.
    * Each alert must have a severity level such as `info`, `warning`, or `critical`, plus a dismissal policy: auto-expire, expire-on-resolution, or manual dismiss.
    * Render active alerts as a stacked client HUD element with newest critical alerts pinned at the top and color/icon treatment consistent with the stone-and-scroll UI theme.
    * Clicking or keyboard-focusing an alert should center the camera on the relevant unit, room, or event source when applicable.
    * Rejected commands must always appear both in the rejection banner and in the durable event/alert history so a player can understand what failed after the banner disappears.

  19) SAVE/LOAD FOR FORTRESS INSTANCES
    * Add per-fortress save slots that persist world state, dwarves, needs, jobs, stockpiles, workshops, structures, multiplayer membership metadata, and the authoritative clock.
    * Save files must include enough data to restore the exact fortress instance after a server restart without creating a new fortress id or losing reconnect compatibility.
    * Add autosave on a fixed tick interval plus manual save from the client settings menu, with authoritative confirmation and failure reporting.
    * Add load-at-startup behavior so the Rust server restores all known fortress instances from disk before accepting client joins.
    * Add explicit conflict rules for manual load while players are connected: either reject the load unless all players confirm, or require the fortress to be empty before load begins.
    * Surface save and load success/failure in both the alert stack and event log, including the fortress name, slot, timestamp, and error reason when relevant.
    * Add browser and server integration tests proving that a saved fortress can be restored with the same visible z-level, selected structures, queued jobs, and multiplayer session
  continuity expectations.

  20) CLIENT SETTINGS MENU
    * Add a native client settings button in the top HUD that opens a modal or panel rendered by the game UI rather than raw browser form layout.
    * The settings menu must include `Save Fortress`, `Load Fortress`, `Quit Fortress`, `Graphics: High/Low`, and `Keybinds`.
    * `Save Fortress` must send an authoritative save request and show progress, success, or rejection from the server instead of pretending the save succeeded locally.
    * `Load Fortress` must list authoritative fortress save slots and require confirmation before replacing the current live fortress state.
    * `Quit Fortress` must disconnect the player cleanly, clear transient client selection state, and return to the fortress create/join menu without leaving stale session UI behind.
    * `Graphics: High/Low` must change real render behavior, not just a label; at minimum, high mode keeps full overlays and richer shading while low mode reduces expensive overlays and
  visual effects.
    * Keybind rebinding must allow the player to change action keys, store them locally per client, validate conflicts, and restore defaults.

  21) DEFAULT CAMERA MOVEMENT KEYS
    * Set `W`, `A`, `S`, and `D` as the default camera pan keys for up, left, down, and right.
    * Keep arrow keys as optional secondary bindings if desired, but render WASD as the primary defaults in the shortcut/help UI.
    * Camera movement must continue to work while the player is in normal gameplay mode and be suppressed when text-entry or key-rebind capture fields are focused.
    * Holding a pan key should continuously move the camera at a deterministic client-side rate that feels smooth but does not alter authoritative world state.
    * The client settings menu must allow rebinding each of the four pan actions independently and restore them to WASD with a `Reset Defaults` action.

  22) DEFAULT Z-LEVEL KEYS
    * Set `Z` as the default key for increasing one z-level upward and `X` as the default key for decreasing one z-level downward, or the inverse if your chosen world-direction convention
  demands it; whichever convention is chosen must be used consistently in UI copy and tests.
    * Pressing either key must issue the same client action path as the current z-level controls, update the visible slice, and preserve reconnect compatibility.
    * The active z-level and the result of each z-level step must remain visible in the top HUD so keyboard-only players always know which slice they are viewing.
    * If the target z-level is out of bounds, reject the step cleanly with no corrupted viewport state and show a visible rejection reason.
    * The settings menu must allow rebinding both z-level actions and restoring them to `Z` and `X`.

  23) KEYBIND HELP AND INPUT DISCOVERABILITY
    * Add a compact help strip or overlay that lists the current primary keybinds for camera pan, z-level changes, task palette, settings, cancel, and any active command mode.
    * When keybinds are changed in settings, the on-screen help must update immediately from the stored binding map rather than hardcoded text.
    * Add a `Reset Controls to Default` action that restores WASD panning and ZX z-level keys in one step.
    * Add automated client tests proving that default WASD and ZX bindings work, that remapped keys replace them correctly, and that focused text inputs suppress gameplay shortcuts.

  24) KEYBOARD-FIRST BUILD PALETTE
    * Pressing `T` then `B` must enter build mode and open a native in-game build palette anchored to the bottom panel or center overlay without using browser prompt dialogs.
    * The palette must immediately focus a text input state so the player can start typing the build target name with no extra click or confirmation step.
    * The palette must support fuzzy matching similar to `fzf`, scoring results against the typed query using item name, aliases, tags, and category labels.
    * The result list must update on every keystroke and always keep one item highlighted as the current selection.
    * Pressing `Tab` must autocomplete the current best match into the input field; if the top result is already fully matched, `Tab` should cycle through close alternatives ordered by
  score and recency.
    * Pressing `ArrowUp` and `ArrowDown` must move the highlighted selection through the current filtered result set without losing the typed query.
    * Pressing `Enter` must confirm the currently highlighted buildable item and transition the client into placement mode for that item.
    * Pressing `Esc` must close the palette and exit build mode cleanly, restoring the previous input state and cursor.

  25) BUILD SEARCH INDEX AND MATCHING RULES
    * Each buildable item must define searchable metadata: `id`, display name, category, aliases, material class, placement type, and unlock requirements.
    * The fuzzy matcher must rank exact prefix matches above substring matches, substring matches above scattered-character fuzzy matches, and all of those above alias-only matches.
    * Recently built items must receive a ranking bonus so commonly used structures rise to the top for short queries.
    * The search system must also consider fortress context, so items that are currently buildable with available materials rank above items that are blocked or unavailable.
    * Locked or unavailable items may still appear in the list, but they must be visually marked and pushed below valid buildable options unless the query strongly matches them.
    * If the query returns no matches, the palette must show a deterministic `No matching build items` state instead of an empty or broken panel.

  26) RECENTLY-USED BUILD CACHE
    * Maintain a per-player recent-build cache keyed by fortress and player id so each player’s build palette learns from what they place most often.
    * The cache must record at least item id, last-used tick or timestamp, and use count, and apply those values as part of result ranking.
    * Recent items must be shown in a dedicated section when the search query is empty, allowing fast access to the player’s normal workflow.
    * Tab-complete should prefer recent items when multiple candidates have similar fuzzy scores.
    * The cache must update only after an authoritative build selection is accepted, not merely when a player highlights an item in the menu.
    * Reconnect should restore the recent-build ordering for that player so the palette remains consistent across sessions.

  27) BUILD PALETTE NAVIGATION AND KEYBOARD UX
    * The palette must show the current query string, highlighted match, total result count, and visible key hints for `Enter`, `Tab`, `ArrowUp`, `ArrowDown`, and `Esc`.
    * Typing printable characters appends to the query, `Backspace` removes one character, and `Ctrl+Backspace` optionally clears the last token or the whole query if supported.
    * The highlighted row must remain stable when the query changes unless the current selection falls out of the filtered result set.
    * Arrow navigation must scroll the result list when the highlight moves beyond the visible window, keeping the active row in view at all times.
    * Mouse interaction may optionally be supported, but the entire flow must remain fully operable from the keyboard with no pointer requirement.
    * The build palette must suppress unrelated gameplay shortcuts while open so typed search text does not accidentally pan the camera or issue commands.

  28) BUILD RESULT ROW CONTENT
    * Every visible search result row must show the item name, category, required materials, placement footprint, and current availability state.
    * Rows for valid buildables must show `ready`, while blocked rows must show explicit reasons such as `missing materials`, `missing workshop`, `missing tech`, or `invalid terrain type`.
    * If a buildable has multiple material variants, the row should indicate the default or last-used variant and allow variant selection in a follow-up subpanel or placement modifier
  flow.
    * The top result should show an expanded preview area with a short description, build time estimate, and dependencies so the player can decide before placement.
    * The UI must visually distinguish exact matches, fuzzy matches, and recent-item boosts so ranking behavior feels predictable.

  29) BUILD PALETTE TO PLACEMENT MODE HANDOFF
    * Confirming a build item from the fuzzy palette must close the search list and switch the cursor into that item’s placement mode immediately.
    * The bottom panel must update to show the selected build item, current material source, footprint size, rotation if applicable, and placement rules.
    * Placement mode must support keyboard cancel, terrain validation, ghost preview rendering, and authoritative rejection feedback if the final placement request is invalid.
    * If the player reopens `TB` while already in placement mode, the palette should preserve the previous query and highlighted item for quick repeated use unless explicitly cleared.
    * Successfully placed items must feed back into the recent-build cache and event log so the next `TB` search gets better over time.

  30) AUTHORITATIVE BUILD CATALOG AND MULTIPLAYER SAFETY
    * The build palette must be populated from authoritative replicated build-catalog data, not from a client-only hardcoded list that can drift from the server.
    * Each catalog entry must include a stable build id, display metadata, unlock state, and current validity rules so all players see the same available options for the same fortress
  state.
    * When another player changes fortress state in a way that affects buildability, such as consuming materials or unlocking a workshop, the build palette must refresh its rankings and
  availability labels on the next tick.
    * Confirming a build item in the palette should only choose the intended item; the actual placement and reservation must still be validated authoritatively at placement time.
    * If a player selects an item that becomes unavailable before placement, the client must preserve the placement mode but surface the authoritative rejection cleanly when placement is
  attempted.

  31) ROAD BUILDING AND SURFACE LOGISTICS SYSTEM
    * Add a dedicated `TR` road designation mode that lets the player paint contiguous surface tiles as planned roads using click-drag placement.
    * A road designation must create authoritative road jobs on the server, not immediate terrain changes on the client.
    * Roads must exist as a distinct tile or overlay type with at least three states: `planned`, `under construction`, and `finished`.
    * Finished roads must visually replace or overlay normal terrain with a clear constructed surface such as packed dirt, stone paving, or wooden trackway.
    * The road system must support basic tile auto-joining so straight segments, corners, T-junctions, and intersections render correctly without manual tile selection.
    * Road placement must be restricted to valid surface terrain unless a separate bridge/ramp feature later expands the placement rules.
    * Invalid placement must produce explicit rejection reasons such as `blocked by structure`, `invalid slope`, `occupied by stockpile`, or `hostile territory`.

  32) ROAD MATERIALS AND CONSTRUCTION JOBS
    * Each road type must define a material requirement and build method, such as packed dirt requiring labor only, stone road requiring stone blocks, and wooden road requiring logs or
  planks.
    * Painting a road creates a batch of construction jobs with per-tile material reservations, worker assignment, and progress tracking.
    * Dwarves with building and hauling labor enabled must gather the required materials from stockpiles or nearby world items before construction begins.
    * If materials are unavailable, the affected road tiles must remain in a `blocked` state and surface the missing material reason in the UI.
    * Construction must proceed tile by tile in a deterministic order so multiplayer clients see the same build sequence and reconnect safely into the same state.
    * Cancelling a planned road must release reserved materials and remove any unstarted jobs without corrupting adjacent road segments.

  33) SURFACE PATHFINDING AND MOVEMENT BONUSES
    * Finished roads must alter authoritative path cost so dwarves strongly prefer traveling on roads for long-distance surface movement.
    * Road preference must be deterministic and apply to hauling, building, patrol, migration, and caravan movement.
    * Different road materials may provide different movement bonuses, but the first implementation can use a single reduced movement-cost modifier for all finished roads.
    * Unfinished or blocked road tiles must not grant path bonuses until construction is complete.
    * Pathfinding must continue to function when roads are partially completed, including rerouting around missing segments and damaged sections.
    * Surface logistics jobs should use roads automatically without requiring a separate player-issued “use road” command.

  34) LOGISTICS RULE SYSTEM
    * Add an authoritative `logistics_rules` model on the server for every stockpile and workshop-capable zone.
    * Each rule must have a stable id, owner zone id, rule type, item filter, source scope, destination scope, min threshold, max threshold, priority, enabled flag, and last evaluation
  tick.
    * Rule evaluation must run on server ticks and create hauling intents/jobs; clients only edit rules and view state.
    * Rules must persist across save/load and reconnect without losing their enabled state or counters.
    * Every rule must expose a live state in the UI: `active`, `satisfied`, `blocked`, `waiting_for_hauler`, `waiting_for_supply`, `destination_full`, or `invalid`.

  35) PULL RULES FOR STOCKPILES AND WORKSHOPS
    * Add `pull` rules that let a zone request goods from valid source stockpiles until the destination inventory reaches a configured target amount.
    * A pull rule must support `maintain at least N`, `fill up to N`, and `exactly N if possible` behaviors.
    * Workshops must be able to declare persistent pull requests for required inputs such as wood, stone blocks, ore, fuel, food, tools, or crafted parts.
    * Pull rules must support item filters by class, subtype, material, quality band, and optional tags such as `edible`, `fuel`, `construction`, or `medical`.
    * If multiple sources can satisfy a pull request, the server must choose deterministically using priority, distance, available surplus, and stable tie-breakers.

  36) PUSH RULES FOR STOCKPILES AND PRODUCERS
    * Add `push` rules that let a source zone automatically export matching goods to one or more destination zones.
    * A push rule must support `push always`, `push when above N`, and `push overflow only` behaviors.
    * Workshops and producer zones must be able to push their outputs automatically to configured destinations such as finished-goods stockpiles, depots, kitchens, or export yards.
    * Push rules must support destination priority lists so the player can prefer one stockpile first and fall back to others only when the preferred destination is full or filtered out.
    * If a push rule has no valid destination, the goods must remain in place and the rule must enter a visible blocked state instead of silently discarding or teleporting items.

  37) WORKSHOP REQUESTER BEHAVIOR
    * Every workshop type must expose an `input request` panel where the player can define persistent desired inventory for each input slot or ingredient class.
    * A workshop request must behave like a standing order: if the workshop falls below the requested amount, pull jobs are created automatically until the target inventory is restored.
    * Workshop requests must be able to distinguish `recipe-bound` requests from `buffer` requests, so a player can keep 5 logs buffered at a carpenter even when no active recipe is
  queued.
    * Input requests must reserve delivery capacity so multiple workshops do not all over-request the same scarce resource in the same tick.
    * The workshop UI must show `requested`, `reserved inbound`, `stored locally`, and `missing` for each requested good.

  38) STOCKPILE PROVIDER BEHAVIOR
    * Every stockpile must expose provider rules that define what it is willing to export and under what conditions.
    * A stockpile provider rule must support `allow export`, `allow export only above reserve`, and `never export`.
    * The player must be able to set a reserve floor for critical goods so a source stockpile does not empty itself below a survival threshold.
    * Provider rules must support directional logistics such as `construction stockpile pushes stone to mason`, `food stockpile pushes meals to tavern`, or `ore yard pushes ore to
  smelter`.
    * The stockpile UI must show how much of each good is globally available, reserved for outbound hauling, and protected by reserve floors.

  39) HAULING JOB GENERATION AND RESERVATION
    * When a push or pull rule becomes actionable, the server must create persistent hauling jobs that reserve a concrete item stack, source tile, and destination tile.
    * Hauling jobs must respect existing item reservations, destination capacity, path access, labor availability, and job priority.
    * A single hauling job should not over-reserve goods needed by another higher-priority requester; conflict resolution must be deterministic and visible.
    * If a reserved source item disappears or changes before pickup, the hauling job must re-evaluate and either retarget or enter a blocked/retry state.
    * Deliveries must be incremental and observable so the player can watch goods move through the fortress instead of appearing instantly.
    * Goods are all carried by dwarves. Free dwarves pick up the items and physically haul them to where they're needed.

  40) UI FOR EDITING RULES
    * Selecting a stockpile or workshop must show a `Logistics Rules` section in the bottom panel with tabs for `Pull`, `Push`, `Requests`, and `Status`.
    * Pressing a keyboard chord such as `VL` (for "view" - "logistics") or opening the zone inspector should allow full keyboard-driven creation and editing of logistics rules.
    * The rule editor must let the player choose rule type, item filters, thresholds, source/destination zones, reserve behavior, priority, and network tags.
    * The UI must support searchable zone selection and searchable item filters so large fortresses remain manageable.
    * Every rule row must show a plain-language summary such as `Pull meals from Food Stockpile until 20 stored` or `Push stone blocks to Mason if above 50`.

  41) DEBUGGING, FEEDBACK, AND TRANSPARENCY
    * Every zone must show current inbound requests, outbound pushes, active hauls, blocked rules, and recent delivery history.
    * Blocked reasons must be explicit and actionable, for example `no matching source`, `all sources reserved`, `destination full`, `path blocked`, `no idle hauler`, or `network mismatch`.
    * Add a fortress-wide logistics overlay or panel that lists the top blocked requests and the busiest supply routes.
    * Clicking a blocked rule should center the camera on the relevant source or destination and highlight the reserved or missing goods.
    * The event log should record important logistics events such as first satisfaction of a request, repeated blockage, reserve-floor starvation, and delivery completion.

  42) RULE TEMPLATES AND DEFAULTS
    * Each workshop type should ship with default request templates, for example a carpenter requests logs and pushes finished beds/doors to furniture storage.
    * Each stockpile type should ship with default provider behavior, for example ore stockpiles export ore, meal stockpiles export food above reserve, and hospital stores protect medical
  reserves.
    * Players must be able to save and apply templates so repeated workshops or stockpiles can reuse the same logistics configuration.
    * Templates must be editable after placement and must not hardcode absolute zone ids; they should resolve destinations by chosen target zones when applied.
    * This makes the system powerful without requiring the player to manually rebuild every rule from scratch.

  43) MULTIPLAYER AND AUTHORITATIVE SAFETY
    * Rule edits must be server-authoritative commands with deterministic ordering so multiple players can edit logistics safely in the same fortress.
    * Conflicting edits to the same rule or zone must resolve deterministically and surface visible acceptance or rejection feedback to all involved players.
    * Reconnect must restore the exact zone rule state, including filters, thresholds, enabled flags, and blocked status.
    * Save/load must preserve rule identity so existing jobs and references can be reconstructed correctly after restart.
    * The client must never simulate deliveries locally; it only renders authoritative job and inventory state.

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

Process requirements (follow strictly)

1. PLANNING FIRST (do this before coding anything):

   * Plan with a milestone plan (at least 50 milestones) that will take hours.
   * For each milestone include: scope, key files/modules, acceptance criteria, and commands to verify.
   * Include a “risk register” with top technical risks and mitigation plans.
   * Include an “architecture overview” section describing:
     * data model
     * overall features
     * client-server approach
     * operations model
     * hunger, crafting, combat, fatigue, sleep, building, enemy, and mining systems

2. SCAFFOLD SECOND:

   * See the `scripts/` dir, as well as the `README.md` and `DESIGN.md` files for scaffolding

3. IMPLEMENT THIRD:

   * Implement one milestone at a time.
   * After each milestone: run verification commands, fix issues, etc.
   * Keep diffs reviewable and avoid giant unstructured changes.

4. REVIEW FOURTH:

   * Review whether the milestone was actually implemented in an adversarial fashion, then if so, commit with a clear message.
   * If the milestone wasn't actually implemented according to spec (both in spirit and letter of the law), perform the necessary fixes, then review again.
   * Use the skills and tools available to you to take screenshots and issue commands to the game to verify the milestone has been implemented.

5. If you hit complexity choices:

   * Prefer correctness and determinism over extra features.
   * Document tradeoffs and decisions in `Documentation.md` as you go.

Start now.
First, create the plan with the complete plan, risk register, and architecture overview.
