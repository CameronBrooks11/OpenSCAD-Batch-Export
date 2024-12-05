import bpy
import math

# USER PARAMETER:
min_spacing = 10  # Minimum spacing between objects

# ----------------------------------
# HELPER FUNCTIONS
# ----------------------------------


def get_bounding_box_size(obj):
    """Return width, height, depth of the object's bounding box."""
    mesh = obj.data
    coords = [obj.matrix_world @ v.co for v in mesh.vertices]
    if not coords:
        return 0, 0, 0
    xs = [v.x for v in coords]
    ys = [v.y for v in coords]
    zs = [v.z for v in coords]
    width = max(xs) - min(xs)
    height = max(ys) - min(ys)
    depth = max(zs) - min(zs)
    return width, height, depth


def arrange_objects_in_square(objects, spacing):
    """
    Arrange objects so they fill a roughly square area:
    1. Calculate total area of objects (based on bounding boxes).
    2. Compute a target square dimension from total area.
    3. Sort objects by size and place them row by row until we run out of space in that row.
       Then start a new row below.

    This is a heuristic approach to mimic slicer arrangements.
    """
    if not objects:
        return

    # Compute bounding box for each object and total area
    object_dims = []
    total_area = 0.0
    for obj in objects:
        w, h, d = get_bounding_box_size(obj)
        # Area in XY plane:
        area = (w + spacing) * (
            h + spacing
        )  # include spacing in the effective footprint
        object_dims.append((max(w, h, d), w, h, obj))
        total_area += area

    # Sort objects by largest dimension first
    object_dims.sort(key=lambda x: x[0], reverse=True)

    # Compute target dimension for the square
    # We'll add a margin factor to ensure we have some extra space
    margin_factor = 1.2
    target_dim = math.sqrt(total_area) * margin_factor

    # Now perform a shelf-packing approach with a max width = target_dim
    current_x = 0.0
    current_y = 0.0
    shelf_height = 0.0

    placed_objects = 0

    for _, w, h, obj in object_dims:
        # Check if we can place this object in the current row
        # If placing it (plus spacing) would exceed target_dim in width, start a new row
        next_x_end = current_x + w + spacing
        if placed_objects == 0:
            # First object, just place it at origin area
            obj.location = (w / 2, h / 2, 0)
            current_x += w + spacing
            shelf_height = h
            placed_objects += 1
        else:
            # If adding this object exceeds the target width, start a new shelf
            if next_x_end > target_dim:
                # Move down by shelf_height + spacing
                current_x = 0.0
                current_y += shelf_height + spacing
                shelf_height = h  # reset shelf height to this object's height
                # Place the object at the start of new shelf
                obj.location = (w / 2, current_y + h / 2, 0)
                current_x = w + spacing
                placed_objects += 1
            else:
                # Place in the same shelf
                obj.location = (current_x + w / 2, current_y + h / 2, 0)
                current_x += w + spacing
                # Update shelf height if this one is taller
                if h > shelf_height:
                    shelf_height = h
                placed_objects += 1

    print(
        f"Arranged {placed_objects} objects in a roughly square layout of dimension ~{target_dim:.2f} units."
    )


# ----------------------------------
# MAIN SCRIPT
# ----------------------------------

# Get all mesh objects in the scene
all_objects = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]

if not all_objects:
    print("No mesh objects found to arrange.")
else:
    arrange_objects_in_square(all_objects, min_spacing)
