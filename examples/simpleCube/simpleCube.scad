// examples/example.scad

// Define default values
width = 10;
height = 10;
depth = 10;

module model()
{
    // Example: A customizable cube
    cube([ width, height, depth ]);
}

// Call the model
model();
