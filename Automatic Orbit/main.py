import time
import krpc

# --- CONFIGURATION ---
TARGET_ALTITUDE = 80000  # 80km orbit
# ---------------------

print("Connecting to KSP...")
try:
    conn = krpc.connect(name='Orbit Master PRO - Fixed', rpc_port=50120, stream_port=50121)
    print("Connected successfully!")
except:
    print("Error: Make sure 'Start Server' is clicked in KSP!")
    exit()

vessel = conn.space_center.active_vessel

# Telemetry Streams
apoapsis = conn.add_stream(getattr, vessel.orbit, 'apoapsis_altitude')
periapsis = conn.add_stream(getattr, vessel.orbit, 'periapsis_altitude')
altitude = conn.add_stream(getattr, vessel.flight(), 'mean_altitude')
speed = conn.add_stream(getattr, vessel.flight(vessel.orbit.body.reference_frame), 'speed')

# --- DETAILED UI TEXT BOX CONFIGURATION ---
canvas = conn.ui.stock_canvas
ui_panel = canvas.add_text("MISSION COMPUTER: INITIALIZING...")
ui_panel.rect_transform.size = (450, 120)
ui_panel.rect_transform.position = (-350, 300)
ui_panel.color = (0.0, 1.0, 0.4)  # Clean Matrix Green
ui_panel.size = 20


def update_hud(phase, extra_text=""):
    ui_panel.content = (
        f"== ORBIT MASTER PRO ==\n"
        f"PHASE: {phase}\n"
        f"ALTITUDE: {altitude() / 1000:.1f} km\n"
        f"APOAPSIS: {apoapsis() / 1000:.1f} km | PERIAPSIS: {periapsis() / 1000:.1f} km\n"
        f"{extra_text}\n"
        f"[BACKSPACE TO MANUALLY ABORT MISSION]"
    )


def check_for_abort():
    """Checks if the user pressed Backspace (Abort Action Group) inside KSP."""
    if vessel.control.abort:
        print("\n!!! EMERGENCY DE-ORBIT PROCEDURE ACTIVATED !!!")
        ui_panel.color = (1.0, 0.1, 0.1)  # Flash HUD Red

        vessel.control.throttle = 0.0
        vessel.control.sas = True
        time.sleep(0.5)

        update_hud("EMERGENCY ABORT", "Locking Retrograde for atmospheric re-entry...")
        vessel.control.sas_mode = conn.space_center.SASMode.retrograde

        # Give the heavy Kerbal X 6 seconds to pivot around backward
        time.sleep(6)

        vessel.control.throttle = 1.0
        update_hud("DE-ORBIT BURN", "Firing engines to guarantee capsule re-entry...")
        time.sleep(6)
        vessel.control.throttle = 0.0

        # --- FIXED FOR KERBAL X STAGING ---
        update_hud("CAPSULE SEPARATION", "Jettisoning tank assembly...")
        vessel.control.activate_next_stage()  # Drops the engine
        time.sleep(1.0)

        update_hud("POD DECOUPLING", "Ejecting main crew pod...")
        vessel.control.activate_next_stage()  # Drops the heavy tank directly beneath the pod
        time.sleep(1.0)

        # Deploy Parachutes via Action Command
        update_hud("DEPLOYING CHUTES", "Opening recovery parachutes...")
        vessel.control.chutes = True  # Activates all parachutes instantly
        vessel.control.activate_next_stage()  # Safeguard: Also hits the final stage layer

        time.sleep(5)
        ui_panel.remove()
        exit()


# Initialize Core Controls
vessel.control.sas = True
vessel.control.throttle = 1.0
vessel.control.abort = False  # Reset abort status indicator

# 3-Second Countdown
for i in range(3, 0, -1):
    update_hud("LAUNCH COUNTDOWN", f"T-Minus {i} seconds...")
    check_for_abort()
    time.sleep(1)

print("LIFT-OFF!")
vessel.control.activate_next_stage()

# --- PHASE 1 & 2: LAUNCH & GRAVITY TURN ---
turn_started = False
while apoapsis() < TARGET_ALTITUDE:
    check_for_abort()
    current_alt = altitude()

    if current_alt > 1000:
        if not turn_started:
            vessel.auto_pilot.engage()
            turn_started = True

        fraction = min(1.0, (current_alt - 1000) / 44000)
        target_pitch = 90.0 - (fraction * 80.0)
        vessel.auto_pilot.target_pitch_and_heading(target_pitch, 90)
        update_hud("GRAVITY TURN", f"Steering East | Target Pitch: {target_pitch:.0f}°")
    else:
        update_hud("VERTICAL ASCENT", "Clearing launch site towers...")

    for engine in vessel.parts.engines:
        if engine.active and not engine.has_fuel:
            vessel.control.activate_next_stage()
            time.sleep(0.5)
            break
    time.sleep(0.05)

# --- PHASE 3: COASTING & SYSTEM DEPLOYMENT ---
vessel.control.throttle = 0.0
vessel.auto_pilot.target_pitch_and_heading(0, 90)
systems_deployed = False

while altitude() < 70000:
    check_for_abort()
    if altitude() > 50000 and not systems_deployed:
        update_hud("SYSTEM DEPLOYMENT", "Deploying solar panels, fairings, and antennas...")
        vessel.control.solar_panels = True
        vessel.control.antennas = True
        vessel.control.toggle_action_group(1)
        systems_deployed = True
        time.sleep(1)

    update_hud("COASTING TO SPACE", f"Time to space: {int((70000 - altitude()) / max(1, speed()))}s")
    time.sleep(0.1)

# --- PHASE 4: SPACE OPERATIONS & INJECTION ---
vessel.control.sas = True
time.sleep(1)
vessel.control.sas_mode = conn.space_center.SASMode.prograde

while vessel.orbit.time_to_apoapsis > 12:
    check_for_abort()
    update_hud("PRE-BURNS ORIENTATION", f"Waiting for Peak | Time to Burn: {vessel.orbit.time_to_apoapsis:.1f}s")
    time.sleep(0.1)

# Circularization Injection Burn
vessel.control.throttle = 1.0
while periapsis() < (TARGET_ALTITUDE - 2000):
    check_for_abort()
    update_hud("CIRCULARIZATION BURN", f"Injecting Rocket Into Safe Orbit...")
    for engine in vessel.parts.engines:
        if engine.active and not engine.has_fuel:
            vessel.control.activate_next_stage()
            break
    time.sleep(0.05)

# Mission Success
vessel.control.throttle = 0.0
vessel.auto_pilot.disengage()
vessel.control.sas_mode = conn.space_center.SASMode.prograde

while True:
    check_for_abort()
    update_hud("MISSION ACCOMPLISHED", "Status: Stable Orbit Established. Computer Idle.")
    time.sleep(1)
