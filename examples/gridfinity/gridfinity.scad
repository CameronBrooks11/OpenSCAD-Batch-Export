// Gridfinity Open Box Examples
// For use in OpenSCAD Batch Exporter project
// Cameron K Brooks 2024

include <gridfinity-rebuilt-openscad/src/core/gridfinity-rebuilt-holes.scad>
include <gridfinity-rebuilt-openscad/src/core/gridfinity-rebuilt-utility.scad>

// Set this to select which example to render
example = 1; // 1 for bin with even spaced grid, 2 for bin with pyramid grid

gx = 6;           // number of bases along x-axis, can be virtually any number
gy = 6;           // number of bases along y-axis, can be virtually any number
height = 5;       // height of the bin, can be virtually any number
scoop_weight = 1; // scoop weight percentage. 0 disabled, 1 is regular; any real number will scale the scoop

n_divx = 3; // only used in example 1, number of X Divisions, can be virtually any number limited by gx
n_divy = 6; // only used in example 1, number of Y Divisions, can be virtually any number limited by gy

// Evenly spaced grid with size of gx by gy and n_divx by n_divy divisions
if (example == 1)
{
    gridfinityInit(gx = gx, gy = gy, h = height(height))
    {
        cutEqual(n_divx = n_divx, n_divy = n_divy, style_tab = 5, scoop_weight = scoop_weight);
    }
    gridfinityBase([ gx, gy ]);
}

// Pyramid scheme bin with size of gx by gy and pyramidal grid of divisions
else if (example == 2)
{
    gridfinityInit(gx = gx, gy = gy, h = height(height))
    {
        for (i = [0:gy - 1])
            for (j = [0:i])
                cut(x = j * gx / (i + 1), y = gy - i - 1, w = gx / (i + 1), h = 1, t = 0, s = scoop_weight);
    }
    gridfinityBase([ gx, gy ]);
}

/*
--> @ cam: keeping this here to remind me to fork and open a pull req to gridfinity main repo to
    fix misuse of x instead of y for cut operations in examples

else if (example == 2)
{
    // You can use loops as well as the bin dimensions to make different parametric functions, such as this one, which
    // divides the box into columns, with a small 1x1 top compartment and a long vertical compartment below
    // Specific to second example
    ratio = 0.3; // 0.0 - 1.0, 0.5 is division in the middle
    hy = gy * (1 - ratio);

    gridfinityInit(gx, gy, height(6), 0, 42)
    {
        for (i = [0:gx - 1])
        {
            cut(x = i, y = 0, w = 1, h = hy, t = style_tab, s = scoop_weight);
            cut(x = i, y = hy, w = 1, h = hy, t = style_tab, s = scoop_weight);
        }
    }
    gridfinityBase([ gx, gy ]);
}
*/