import time
import krpc

# 1. Establish connection to the game using your custom port mappings
try:
    conn = krpc.connect(
        name='Lynx Gravity Recreation (Custom Ports)',
        address='127.0.0.1',
        rpc_port=50120,      # Your custom RPC communication port
        stream_port=50121    # Your custom high-speed data stream port
    )
    space_center = conn.space_center
    vessel = space_center.active_vessel
    body = vessel.orbit.body
    print(f"Connected on ports 50120/50121! Modifying planet: {body.name}")
except ConnectionRefusedError:
    print("Error: Could not connect. Double check that the kRPC server inside KSP")
    print("is started and set to RPC: 50120 and Stream: 50121.")
    exit()

# 2. Cache baseline parameters for safe recovery down the line
ORIGINAL_GRAV_PARAMETER = body.gravitational_parameter
ORIGINAL_SURFACE_G = body.surface_gravity

# Establish high-speed telemetry feed
flight = vessel.flight(body.reference_frame)
altitude_stream = conn.add_stream(getattr, flight, 'surface_altitude')

print("Dynamic planetary mass alteration loop engaged. Fly safely.")

try:
    while True:
        # Pull instant flight data step
        absolute_altitude = altitude_stream()
        
        # Exact mathematical equation from the YouTuber's screenshot
        new_gravity_in_g = (absolute_altitude * 0.00008) + 1.0
        
        # Translate G-forces into the engine's internal Keplerian parameters (GM)
        new_grav_parameter = (new_gravity_in_g * 9.80665) * (ORIGINAL_GRAV_PARAMETER / ORIGINAL_SURFACE_G)
        
        # Override the planetary field calculation
        body.gravitational_parameter = new_grav_parameter
        
        # Update user interface text overlay layout
        space_center.clear_messages()
        space_center.hud_show_message(
            f"Current Gravity = {new_gravity_in_g:.4f} G", 
            duration=0.05, 
            style=space_center.HUDMessageType.vessel_status
        )
        
        # Match game frame timing updates (~50Hz rate)
        time.sleep(0.02)

except KeyboardInterrupt:
    # 3. Clean environment parameters upon manual stop execution
    print("\nScript stopped. Returning celestial bodies to normal tracking weight.")
    body.gravitational_parameter = ORIGINAL_GRAV_PARAMETER
