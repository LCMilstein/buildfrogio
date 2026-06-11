// DAC Extension Collar for Raspberry Pi Zero + Waveshare + InnoMaker DAC stack
// This script creates a stackable collar that sits on top of the existing Pihole/piSlice case
// and provides cutouts for the InnoMaker DAC Mini ports.

// ==========================================
// PARAMETERS
// ==========================================

// Height of the extension collar (adjust based on the height of your standoffs + DAC)
extension_height = 20; 

// Wall thickness to match the base case
wall_thickness = 2;

// The base STL to use for matching the profile. 
// Change this path if using the piSlice case or if the STL is in another directory.
base_stl = "temp/pihole/files/pihole-case-top.stl";
slice_z_height = -2; // The Z height at which to take a 2D cross-section of the base STL

// --- Port Cutouts ---
// Adjust the X, Y, Z positions based on the physical InnoMaker DAC Mini measurements.
// Sizes match typical HifiBerry / InnoMaker RCA & 3.5mm jacks.

rca_radius = 5.5;
minijack_radius = 4.5;

// Heights (Z from the bottom of this collar)
port_z = 10; 

// Horizontal positions (X along the edge)
rca_left_x = 15;
rca_right_x = 28;
minijack_x = 45;

// Port Face (Set to front/back/left/right depending on orientation)
// We assume they sit on one of the long edges (Y axis face).
y_face_offset = 0; // Adjust if the ports need to pierce a different face

// ==========================================
// GEOMETRY GENERATION
// ==========================================

difference() {
    // 1. Outer Profile: Extrude the 2D cross-section of the base case
    linear_extrude(height=extension_height) {
        projection(cut=true) {
            translate([0, 0, slice_z_height]) 
            import(base_stl);
        }
    }
    
    // 2. Inner Hollow: Offset the profile inwards to create walls
    translate([0, 0, -1])
    linear_extrude(height=extension_height + 2) {
        offset(r=-wall_thickness) {
            projection(cut=true) {
                translate([0, 0, slice_z_height]) 
                import(base_stl);
            }
        }
    }

    // 3. Port Cutouts
    // Left RCA
    translate([rca_left_x, y_face_offset, port_z])
    rotate([90, 0, 0])
    cylinder(h=50, r=rca_radius, center=true, $fn=50);

    // Right RCA
    translate([rca_right_x, y_face_offset, port_z])
    rotate([90, 0, 0])
    cylinder(h=50, r=rca_radius, center=true, $fn=50);

    // 3.5mm Minijack
    translate([minijack_x, y_face_offset, port_z])
    rotate([90, 0, 0])
    cylinder(h=50, r=minijack_radius, center=true, $fn=50);
}

// Note: To add a roof/lid, you can either print another solid cross-section 
// or print the original case top and place it on top of this collar.
