# 3D Workshop & Build123d System Prompt Guidelines

When assisting a user with modifying or extending 3D CAD files (STEP/STL) using `build123d` in the 3D-Workshop environment, adhere to the following strict guidelines to prevent catastrophic printing failures and excessive iteration.

## 1. Never blindly slice and extrude STEP files without inspecting internal geometry
When you split a STEP file (e.g. `bd.split()`) and translate a section upwards to create an extension, you carry **all** of the original internal geometry with it. 
*   **The Trap:** If the top section of the original case contained a built-in roof, mounting posts, screw holes, or structural hexagonal cutouts, those features will move up with your slice and block the internal cavity of the extension, ruining the print.
*   **The Solution:** Use `hollowing` techniques. Before splitting the part, subtract an inner bounding box (e.g., `bd.RectangleRounded` matched to the inner dimensions) from the inside of the case to completely obliterate internal overhangs, posts, and roofs in the section you are extending. This guarantees a clean, un-obstructed wall.

## 2. Perfecting the "Seamless" Collar (No Lips or Overhangs)
If you try to bridge a gap using generic geometric primitives (like `bd.RectangleRounded(70, 35, 3.0)`), it will likely create a visual lip or seam because you missed the original model's precise corner radius, draft angles, or chamfers.
*   **The Trap:** Assuming standard measurements match the STL/STEP perfectly.
*   **The Solution:** Extract the *exact mathematical cross-section* of the original model. 
    ```python
    # Split the base and extract the topmost face
    bottom = bd.split(clean_base, bd.Plane(origin=(0,0,z_split), z_dir=(0,0,1)), keep=bd.Keep.BOTTOM)
    top_face = bottom.faces().filter_by(bd.Axis.Z).sort_by(bd.Axis.Z)[-1]
    
    # Extrude that exact face to form the collar
    collar_part = bd.extrude(top_face, amount=extension_height)
    ```

## 3. Designing Friction-Fit Lids
When the user asks for a flush, snap-on lid, it must consist of a flat top plate and an inner friction plug.
*   **The Trap:** Creating the lid components at the Z-height of the case top (e.g. Z=26) and the friction lip at a different height, causing them to render as disconnected floating plates.
*   **The Solution:** 
    1.  Move the case's `outer_wire` down to `Z=0` and extrude it by 2mm. This creates the flush top plate.
    2.  Create a sketch for the inner friction lip at `Z=2.0` (offsetting the inner cavity by `-0.2mm` for tolerance) and extrude it by 2mm.
    3.  Merge them into a single solid part (`lid_plate + lip_part.part`).
    4.  Keep the lid flat on `Z=0` so it prints without supports!

## 4. Port Cutouts and Z-Height Alignment
Hardware boards (like a Raspberry Pi + Ethernet HAT + DAC) stack vertically.
*   **The Trap:** Assuming ports are centered on the board, or assuming the Z-height of a port is flush with the bottom of its board. Some components (like RCA terminals) are elevated above the PCB by a plastic block (e.g., +4.4mm).
*   **The Solution:** When determining extension height, ensure the extension fully clears the highest component of the stack (e.g., RCA top edge). Always calculate port X-coordinates relative to the *center* of the board if the user provides left/right gap measurements, rather than trying to measure from the absolute case wall coordinates.

## 5. Bottom Case Cleanups
If the user is repurposing a case, the original bottom may have screw holes meant for a lid that is no longer being used.
*   **The Solution:** Create a flush 2mm floor (`bd.extrude` a `bd.RectangleRounded` at `Z=0`) and union it with the base to cleanly fill unwanted screw holes while maintaining the case exterior.
