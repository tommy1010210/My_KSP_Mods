import time
import krpc

print("Connecting to KSP...")
try:
    conn = krpc.connect(name='Gameslinx Translation - True TWR', rpc_port=50120, stream_port=50121)
    print("Connected successfully!")
except:
    print("Error: Make sure 'Start Server' is clicked in KSP!")
    exit()

vessel = conn.space_center.active_vessel

# Real-world surface gravity factor baseline
SURFACE_GRAVITY = 9.81

print("\n--- SYNCHRONIZED TWR LOOP RUNNING ---")
message_timer = 0

while True:
    try:
        # Get absolute altitude above sea level
        absolute_altitude = vessel.flight().mean_altitude

        # --- CALCULATE GAMESLINX MATH CONTINUOUSLY ---
        # This guarantees the TWR math registers from 0 meters up!
        gravity_multiplier = (absolute_altitude * 0.00008) + 1.0

        # Crash governor ceiling
        if gravity_multiplier > 15.0:
            gravity_multiplier = 15.0

        extra_g_acceleration = (gravity_multiplier - 1.0) * SURFACE_GRAVITY

        # --- PHYSICS FORCE CEILING OVERLAY ---
        # Only apply the physical downward penalty once we leave the pad safety cushion
        if absolute_altitude > 100:
            torque_free_position = (0.0, 0.0, 0.0)

            for part in vessel.parts.all:
                try:
                    part_mass = part.mass
                    part_force = part_mass * extra_g_acceleration

                    # Z-axis is pure vertical down inside surface_reference_frame matrix
                    downward_vector = (0.0, 0.0, -part_force)
                    part.add_force(downward_vector, torque_free_position, vessel.surface_reference_frame)
                except:
                    continue

        # --- RE-CALCULATE ACCURATE MANIPULATED TWR ENGINE VALUE ---
        total_mass_kilograms = vessel.mass * 1000
        current_thrust_newtons = vessel.thrust

        # Total Weight = Mass * (Normal Gravity + Our Added Challenge Acceleration)
        true_weight_newtons = total_mass_kilograms * (SURFACE_GRAVITY + extra_g_acceleration)

        if true_weight_newtons > 0:
            true_twr = current_thrust_newtons / true_weight_newtons
        else:
            true_twr = 0

        # --- ON-SCREEN BANNER TRACKING ---
        message_timer += 1
        if message_timer >= 5:
            ui_text = f"GRAVITY: {gravity_multiplier:.2f} Gs  |  REAL TWR: {true_twr:.2f}"
            conn.ui.message(ui_text, duration=0.15)
            print(f"Alt: {absolute_altitude:.0f}m | {ui_text}", end="\r")
            message_timer = 0

        time.sleep(0.02)

    except krpc.error.RPCError:
        print("\nConnection lost or rocket destroyed.")
        break
