import time
import krpc

# --- CONFIGURATION ---
TARGET_ALTITUDE = 80000  # 80km orbit
# ---------------------

print("Connecting to KSP...")
try:
    conn = krpc.connect(name='Universal Autopilot - Optimized Cutoff', rpc_port=50120, stream_port=50121)
    print("Connected successfully!")
except:
    print("Error: Make sure 'Start Server' is clicked in KSP!")
    exit()

vessel = conn.space_center.active_vessel

# Core Telemetry Streams
apoapsis = conn.add_stream(getattr, vessel.orbit, 'apoapsis_altitude')
periapsis = conn.add_stream(getattr, vessel.orbit, 'periapsis_altitude')
altitude = conn.add_stream(getattr, vessel.flight(), 'mean_altitude')
speed = conn.add_stream(getattr, vessel.flight(vessel.orbit.body.reference_frame), 'speed')

# --- HUD PANEL SETUP ---
canvas = conn.ui.stock_canvas
ui_panel = canvas.add_text("MISSION COMPUTER: INITIALIZING...")
ui_panel.rect_transform.size = (450, 140)
ui_panel.rect_transform.position = (-350, 300)
ui_panel.color = (0.0, 1.0, 0.4)  # Matrix Green
ui_panel.size = 20


def update_hud(phase, extra_text=""):
    """Refreshes the on-screen display panel with current flight phase and data."""
    ui_panel.content = (
        f"== ORBIT MASTER: INTELLIGENT EYE ==\n"
        f"ACTIVE VESSEL: {vessel.name}\n"
        f"PHASE: {phase}\n"
        f"ALTITUDE: {altitude() / 1000:.1f} km\n"
        f"APOAPSIS: {apoapsis() / 1000:.1f} km | PERIAPSIS: {periapsis() / 1000:.1f} km\n"
        f"{extra_text}\n"
        f"[BACKSPACE TO MANUALLY ABORT]"
    )


def check_for_abort():
    """Monitors KSP's abort group and triggers a smart vector-aligned recovery sequence."""
    if vessel.control.abort:
        print("\n!!! EMERGENCY INTEL-ABORT SYSTEM ENGAGED !!!")
        ui_panel.color = (1.0, 0.1, 0.1)  # Flash HUD Red

        vessel.control.throttle = 0.0
        active_engines = [e for e in vessel.parts.engines if e.active and e.has_fuel]

        if active_engines:
            update_hud("EMERGENCY RETRO-ALIGN", "Swinging ship around to face Retrograde...")
            vessel.auto_pilot.engage()
            planet_frame = vessel.orbit.body.reference_frame

            while True:
                forward_orbital_vector = vessel.flight(planet_frame).prograde
                retrograde_target = (-forward_orbital_vector, -forward_orbital_vector, -forward_orbital_vector)
                vessel.auto_pilot.target_direction = retrograde_target

                current_nose_vector = vessel.flight(planet_frame).direction
                dot_product = sum(a * b for a, b in zip(current_nose_vector, retrograde_target))
                dot_product = max(-1.0, min(1.0, dot_product))
                import math
                angle_error_degrees = math.degrees(math.acos(dot_product))

                if angle_error_degrees < 4.0:
                    break
                time.sleep(0.05)

            vessel.control.throttle = 1.0
            update_hud("DE-ORBIT BURN", "Firing engines to guarantee re-entry...")
            time.sleep(5)
            vessel.control.throttle = 0.0
            vessel.auto_pilot.disengage()

        update_hud("VESSEL JETTISON", "Clearing lower vehicle attachments...")
        vessel.control.sas = True
        while vessel.control.current_stage > 0:
            try:
                vessel.control.activate_next_stage()
                time.sleep(0.4)
            except:
                break

        update_hud("CAPSULE RECOVERY", "Deploying safety recovery parachutes...")
        vessel.control.chutes = True
        time.sleep(5)
        ui_panel.remove()
        exit()


def execute_intelligent_staging():
    """Scans the active parts tree and stages dynamically if any engine group runs dry."""
    active_engines = [e for e in vessel.parts.engines if e.active]
    if not active_engines:
        return

    should_stage = False
    for engine in active_engines:
        if not engine.has_fuel:
            should_stage = True
            break
        if engine.part.stage == vessel.control.current_stage and engine.thrust == 0.0:
            should_stage = True
            break

    if should_stage:
        print("\n[STAGING BRAIN]: Flameout detected. Executing clean decoupling...")
        vessel.control.activate_next_stage()
        time.sleep(0.6)


# Initialize Core Autopilot Controls
vessel.control.sas = True
vessel.control.throttle = 1.0
vessel.control.abort = False

# Countdown
for i in range(3, 0, -1):
    check_for_abort()
    update_hud("LAUNCH COUNTDOWN", f"T-Minus {i} seconds...")
    time.sleep(1)

print("LIFT-OFF!")
vessel.control.activate_next_stage()

# --- PHASE 1 & 2: LAUNCH & AUTOMATED GRAVITY TURN ---
turn_started = False
# FIXED: Shuts down main engines 5,000 meters early to account for coasting momentum!
while apoapsis() < (TARGET_ALTITUDE - 5000):
    check_for_abort()
    current_alt = altitude()
    execute_intelligent_staging()

    if current_alt > 1000:
        if not turn_started:
            vessel.auto_pilot.engage()
            turn_started = True

        fraction = min(1.0, (current_alt - 1000) / 44000)
        target_pitch = 90.0 - (fraction * 80.0)
        vessel.auto_pilot.target_pitch_and_heading(target_pitch, 90)
        update_hud("GRAVITY TURN", f"Steering East | Target Pitch: {target_pitch:.0f}°")
    else:
        update_hud("VERTICAL ASCENT", "Clearing launch pad towers...")

    time.sleep(0.02)

# --- PHASE 3: COASTING TO SPACE & DEPLOYMENT ---
vessel.control.throttle = 0.0
vessel.auto_pilot.target_pitch_and_heading(0, 90)
systems_deployed = False

while altitude() < 70000:
    check_for_abort()
    execute_intelligent_staging()

    if altitude() > 50000 and not systems_deployed:
        update_hud("SYSTEM DEPLOYMENT", "Deploying solar panels and antennas...")
        vessel.control.solar_panels = True
        vessel.control.antennas = True
        vessel.control.toggle_action_group(1)
        systems_deployed = True
        time.sleep(1)

    time_to_space = int((70000 - altitude()) / max(1, speed()))
    update_hud("COASTING TO SPACE", f"Time to space boundary: {time_to_space}s")
    time.sleep(0.02)

# --- PHASE 4: SPACE OPERATIONS & CIRCULARIZATION ---
vessel.control.sas = True
time.sleep(1)
vessel.control.sas_mode = conn.space_center.SASMode.prograde

while vessel.orbit.time_to_apoapsis > 12:
    check_for_abort()
    update_hud("PRE-BURNS ORIENTATION", f"Waiting for Peak | Time to Burn: {vessel.orbit.time_to_apoapsis:.1f}s")
    time.sleep(0.02)

# Execute the final circularization injection burn
vessel.control.throttle = 1.0
while periapsis() < (TARGET_ALTITUDE - 2000):
    check_for_abort()
    execute_intelligent_staging()
    update_hud("CIRCULARIZATION BURN", f"Injecting Rocket Into Safe Orbit...")
    time.sleep(0.02)

# Mission Success Evaluation
vessel.control.throttle = 0.0
vessel.auto_pilot.disengage()
vessel.control.sas_mode = conn.space_center.SASMode.prograde

while True:
    check_for_abort()
    update_hud("MISSION ACCOMPLISHED", "Status: Stable Orbit Established. Computer Idle.")
    time.sleep(1)
