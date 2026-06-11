include <hinge.scad>

$fn=80;

//*
//#
//color("white")
//translate([-0.8,0,3])
//translate([-69.3, 44.5, 14])
//scale([25.4, 25.4, 25.4])
//import("hifiberry-dac-plus-adc-1.2.stl"); 

//*
*
translate([-10-0.8, 0, 4])
color("white")
import("RPi_4_dummy.stl");

width=65;
height=36;
length=95.6;
bottom_thickness=2.5;

straight_hole_rim=0.8;
extra = 0;

screw_hole_radius=1.5;
screw_head_radius=2.67;
screw_head_depth=4.15;

corner_edge_radius = 3;

//hinge-parameters
horizontal_distance=3;
hinge_radius=2;
number_of_hinge_parts=8;
extra_hinge_corner_height=1;
hinge_tolerance=0.3;

//ventilation hole tuning. Not complete
holes_in_back=false;
holes_in_side=true;
vertical_number_of_holes=4;
horizontal_number_of_holes=5;
hole_radius=4;
hole_rim=1.1;
vertical_hole_rim = 6;



//slide or hinge
top_type="slide";


//some calculations depending on the variables before
side_height = top_type == "slide" ? 
    height + bottom_thickness 
    : height;
side_translate_height = top_type == "slide" ?
            (height)/2
            :(height-bottom_thickness)/2;

//"top" or "case" or "all"
part = "top";
if(top_type == "hinge") {
    rotate([90,0,0])
    case();
} else if (top_type == "slide" && part == "top") {
    rotate([-90,0,0])
    case();
} else {
    case();
}

module case() {
    difference() {
        union() {
            if(part == "all" || part == "case") {
                bottom();
                
                difference() {
                    front();
                    pi4_holes_front();
                }
                
                difference() {
                    sides();
                    pi4_holes_side();

                }
                color("brown")
                board_supports();
                holes_outer();
            }

            
        }
                   
        if(part == "all" || part == "case") {
            sd_card_slot();
            holes_inner();
            if(top_type=="slide") {
           //     back_lips(0.05);
            }
        }
        
    }
    if(part == "all" || part == "top") {            
        top();        
        difference() {

            back();
            holes_inner();
        }
    }
}


module back_lips(extra=0) {
    x_distance_from_edge = 2.2;
    distance_from_edge = 8.05;
    distance_from_utp = 29.6;
    union() {

        height=1.2+extra;
        radius=3.5+extra;

        color("green")
        translate([-length/2+distance_from_edge, width/2-distance_from_edge, 5.3-height-1.25])
        cylinder(r=radius, h=height+extra, center=false);
        
        translate([-length/2+distance_from_edge-radius, width/2-distance_from_edge, 5.3-height-1.25])
        cube([radius*2,radius*2, height+extra]);
        translate([-length/2+distance_from_edge-radius, width/2-x_distance_from_edge*2, 5.3-height-1.25])
        cube([radius*2,x_distance_from_edge, 2.5]);


        color("green")
        translate([length/2-distance_from_utp, width/2-distance_from_edge, 5.3-height-1.25])        
        cylinder(r=radius, h=height+extra, center=false);
        
        translate([length/2-radius-distance_from_utp, width/2-distance_from_edge, 5.3-height-1.25])
        cube([radius*2,radius*2, height+extra]);
        
        translate([length/2-radius-distance_from_utp, width/2-x_distance_from_edge*2, 5.3-height-1.25])
        cube([radius*2,x_distance_from_edge, 2.5]);

    }
}

module holes_outer() {

    distance_from_edge = 8.05;
    distance_from_utp = 29.6;
    radius2 = top_type == "slide" ? 
            3.5 : 3.5;
    height2 = top_type == "slide" ? 
            5.3 -1.2: 5.3;
    color("white")
    translate([-length/2+distance_from_edge, -width/2+distance_from_edge, -1.25])
    cylinder(r1=7,r2=3.5, h=5.3, center=false);
    color("white")

    translate([-length/2+distance_from_edge, width/2-distance_from_edge, -1.25])
    cylinder(r1=7,r2=radius2, h=height2, center=false);

    color("white")
    translate([length/2-distance_from_utp, -width/2+distance_from_edge, -1.25])
    cylinder(r1=7,r2=3.5, h=5.3, center=false);
    color("white")
    translate([length/2-distance_from_utp, width/2-distance_from_edge, -1.25])
    cylinder(r1=7,r2=radius2, h=height2, center=false);

}

module board_supports() {
    x_distance_from_edge = 2.5;
    y_distance_from_edge = 7.05;
    distance_from_utp = 29.6;
    
    //viewed from top, UTP to the right:
    //left-top hole, left support
    translate([-length/2+x_distance_from_edge, -width/2+y_distance_from_edge, 0])
    board_support();
    
    //left-top hole, top support
    if(top_type=="hinge") {
        translate([-length/2+x_distance_from_edge+4.5, width/2-y_distance_from_edge+4.6, 0])
        rotate([0,0,-90])    
        board_support();
    }
    //left-bottom hole, left support
    difference() {
        translate([-length/2+x_distance_from_edge, width/2-y_distance_from_edge-2, 0])
        board_support();
        back_lips(extra=0.05);
    }
    
    //left-top hole, bottom support
    translate([-length/2+y_distance_from_edge+2, -width/2+x_distance_from_edge-0.05, 0])
    rotate([0,0,90])    
    board_support();

    //right-top hole, top support    
    if(top_type=="hinge") {
        translate([length/2-distance_from_utp-1, width/2-y_distance_from_edge+4.6, 0])
        rotate([0,0,-90])    
        board_support();
    }
    
    //right-bottom hole, bottom support       
    translate([length/2-distance_from_utp+1, -width/2+x_distance_from_edge-0.05, 0])
    rotate([0,0,90])    
    board_support();
    
    //right-top support
    
    translate([length/2-x_distance_from_edge, width/2-y_distance_from_edge-15.9, 0])
    rotate([0,0,180])    
    board_support(width=2.7, slope=true);

    //right-bottom support    
    translate([length/2-x_distance_from_edge, -width/2+y_distance_from_edge+16.7, 0])
    rotate([0,0,180])    
    board_support(width=2.5, slope=true);
    
}

module board_support(width=2, slope=false) {
 
    top_height=5;
    bottom_height=4.05;

    top_length=1.85;
    length=6;
    extra_cutoff_height=0.75;

    difference() {
        cube([top_length, width, top_height]);

    color("cyan")
            translate([-1.3,-0.1,top_height+extra_cutoff_height])
     rotate([0,30,0])
        cube([top_length*3, width+0.2, top_length*3]);        
       
    }

    cube([length, width, bottom_height]);
    if(slope) {
        
        translate([length,width,bottom_height/2])
        rotate([0,-90,0])
        linear_extrude(height=length, center=false)
         circle(d=bottom_height, $fn=3 );
    }
        
}


module holes_inner() {
    color("white")
    translate([-length/2+8.05, -width/2+8.05, -1.3])
    cylinder(r=screw_hole_radius, h=5.8, center=false);

    color("blue")
    translate([-length/2+8.05, -width/2+8.05, -1.3])
    cylinder(r=screw_head_radius, h=screw_head_depth, center=false);
    
    color("white")
    translate([-length/2+8.05, width/2-8.05, -1.3])
    cylinder(r=screw_hole_radius, h=5.8, center=false);
    color("blue")
    translate([-length/2+8.05, width/2-8.05, -1.3])
    cylinder(r=screw_head_radius, h=screw_head_depth, center=false);
    
    color("white")
    translate([length/2-29.6, -width/2+8.05, -1.3])
    cylinder(r=screw_hole_radius, h=5.8, center=false);
    color("blue")
    translate([length/2-29.6, -width/2+8.05, -1.3])
    cylinder(r=screw_head_radius, h=screw_head_depth, center=false);
    
    color("white")
    translate([length/2-29.6, width/2-8.05, -1.3])
    cylinder(r=screw_hole_radius, h=5.8, center=false);
    color("blue")
    translate([length/2-29.6, width/2-8.05, -1.3])
    cylinder(r=screw_head_radius, h=screw_head_depth, center=false);
}

module bottom() {

    difference() {
        color("red")
        cube([length, width, bottom_thickness], true);
        right_corner();
        
        left_corner();
    }
}


module front() {

    
    difference() {
        translate([0, -(width-bottom_thickness)/2,side_translate_height])
        color("blue")
        rotate([90,0,0])
        cube([length, side_height, bottom_thickness], true);   
        right_corner();
        left_corner();
    }    
    
}

module left_corner() {

    translate([-length/2+corner_edge_radius, -width/2+corner_edge_radius, 0])
    color("teal")
    difference() {
        translate([-corner_edge_radius, -corner_edge_radius, -bottom_thickness/2])
        cube([corner_edge_radius, corner_edge_radius,height+bottom_thickness]);
        translate([0,0, -bottom_thickness/2])
        cylinder(h=height+bottom_thickness*2+0.2, r=corner_edge_radius);
    }
    
    translate([-length/2+corner_edge_radius, width/2-corner_edge_radius, 0])
    color("teal")
    difference() {
        translate([-corner_edge_radius, 0, -bottom_thickness/2])
        cube([corner_edge_radius, corner_edge_radius,height+bottom_thickness]);
        translate([0,0, -bottom_thickness/2])
        cylinder(h=height+bottom_thickness*2+0.2, r=corner_edge_radius);
    }
}

module right_corner() {
    translate([length/2-corner_edge_radius, -width/2+corner_edge_radius, 0])
    color("teal")
    difference() {
        translate([0, -corner_edge_radius, -bottom_thickness/2])
        cube([corner_edge_radius, corner_edge_radius,height+bottom_thickness]);
        translate([0,0, -bottom_thickness/2])
        cylinder(h=height+bottom_thickness*2+0.2, r=corner_edge_radius);
    }
    
    translate([length/2-corner_edge_radius, width/2-corner_edge_radius, 0])
    color("teal")
    difference() {
        translate([0, 0, -bottom_thickness/2])
        cube([corner_edge_radius, corner_edge_radius,height+bottom_thickness]);
        translate([0,0, -bottom_thickness/2])
        cylinder(h=height+bottom_thickness*2+0.2, r=corner_edge_radius);
    }
}


module back() {    
    if(top_type == "hinge") {
        tolerance = 0.1;
        difference() {
            
            translate([0, -(width-bottom_thickness)/2,height+(height-bottom_thickness-tolerance-hinge_tolerance/2)/2+bottom_thickness + 1.5])
            color("orange")
            rotate([90,0,0])
            cube([length-bottom_thickness*2-tolerance*2, height-bottom_thickness-tolerance, bottom_thickness], true);
            //ventilation again

            if(holes_in_back) {
                union() {
                  for(j = [0:vertical_number_of_holes-1]) {
                    for(i=[-horizontal_number_of_holes/2:horizontal_number_of_holes/2]) {
                           color("cyan")
                           translate([hole_radius-(j%2)*(hole_radius+vertical_hole_rim/2)+i*(hole_radius*2+vertical_hole_rim), -width/2 ,height*1.35+j*(hole_radius+hole_rim)])
                           rotate([90,0,0])
                           linear_extrude(height=10, center=true)
                           circle(r=hole_radius,$fn=6);
                       }
                  }
              }
           }
        }
    } else {
        tolerance=0.2;
        difference() {
            translate([0,width/2-bottom_thickness/2, height/2+tolerance/2])
            cube([length-bottom_thickness*2-tolerance*2, bottom_thickness, height-bottom_thickness-tolerance], center=true);
           slide_rails(0.2);
            if(holes_in_back) {
                translate([0,width/2,height/2-8])
                rotate([0,0,0])
                holes();
            }
        }
        back_lips();

    }
}


module holes(vertical_number_of_holes=4) {
     for(j = [0:vertical_number_of_holes-1]) {
                    for(i=[-horizontal_number_of_holes/2:horizontal_number_of_holes/2]) {
                           color("cyan")
                           translate([hole_radius-(j%2)*(hole_radius+vertical_hole_rim/2)+i*(hole_radius*2+vertical_hole_rim), 0 ,j*(hole_radius+hole_rim)])
                           rotate([90,0,0])
                           linear_extrude(height=10, center=true)
                           circle(r=hole_radius,$fn=6);
                       }
                  }
}


module top() {

    if(top_type == "hinge") {
        hinge_top();
    } else {
        slide_top();
    }
}

module slide_top() {
    tolerance=0.2;
    difference() {
        color("purple")
        translate([0, bottom_thickness/2+tolerance/2, height])
        cube([length-bottom_thickness*2-tolerance, width-bottom_thickness-tolerance, bottom_thickness], center=true);
        slide_rails(tolerance);
        translate([0, width/2-8, height])
        rotate([90,0,0])
        holes(vertical_number_of_holes=10);
    }

}

module hinge_top() {
    hinge_corner_height=hinge_radius*2+extra_hinge_corner_height;
    extra_hinge_height=hinge_radius+extra_hinge_corner_height;
    echo("test", extra_hinge_height);

    
    
    difference() {
       translate([-length/2,-hinge_radius*2-extra_hinge_height/2,height+1.2])
       rotate([-90, 0,0])
       applyHinges([[0,0,0]], [0,0,0], hinge_radius, hinge_corner_height, length, number_of_hinge_parts, hinge_tolerance) {
            union() {                
                translate([0,0,hinge_radius*2-(width-extra_hinge_height)/2])
                cube([length, bottom_thickness, (width-extra_hinge_height)/2]);
                translate([0,-horizontal_distance+hinge_tolerance/2,hinge_radius*2-(width-extra_hinge_height)/2])
                cube([length, bottom_thickness-hinge_tolerance/2, (width-extra_hinge_height)/2]);
            }
        }
        //ventilation again

        union() {
            for(j = [0:vertical_number_of_holes-1]) {
                for(i=[-horizontal_number_of_holes/2:horizontal_number_of_holes/2]) {
                    color("cyan")
                    translate([hole_radius-(j%2)*(hole_radius+vertical_hole_rim/2)+i*(hole_radius*2+vertical_hole_rim), -7.5-j*(hole_radius+hole_rim), height])
                    linear_extrude(height=10, center=true)
                    circle(r=hole_radius,$fn=6);
                }
            }
        }
        //rounded edges
        right_corner();
        left_corner();
    }    
}

module sides() {
   
    difference() {
        union() {
            difference() {
                translate([-length/2+bottom_thickness/2, 0,side_translate_height])
                color("green")
                rotate([0,90,0])
                cube([side_height, width, bottom_thickness], true);
                 if(holes_in_side) {
                     //5 ventilation holes on the side
                     union() {
                        for(i=[-2:2]) {
                            color("cyan")
                            translate([-length/2+bottom_thickness/2, i*12,(height-bottom_thickness)/3])
                            rotate([0,90,0])
                            linear_extrude(height=10, center=true)
                            circle(r=4,$fn=6);
                        }
                    }
                }
   
             }   
            
            difference() {
                //UTP side
                translate([length/2-bottom_thickness/2, 0,side_translate_height])
                color("green")
                rotate([0,90,0])
                cube([side_height, width, bottom_thickness], true);
                right_corner();
            }
            if(top_type == "slide") {
                slide_rails();
            }
        }
        left_corner(); 
        right_corner();
    }
        

}

module slide_rails(extra_radius=0) {
    top_rail_thickness=2.5;
    rail_radius=0.9;
    vertical_rail_width=1.2;

    distance_from_top=0.4;
    rail_distance = top_rail_thickness-rail_radius-distance_from_top;
    
    vertical_rail_height = height-(bottom_thickness+0.2);

    //left+right rails
    for(side = [-1:2:1]) {
        for(i = [0]) {
            translate([side*(-length/2+bottom_thickness), 
                width/2, 
                height+bottom_thickness/2-rail_radius-i*rail_distance-distance_from_top])
            scale([1.5, 1, 1])
            rotate([90,90,0])
            linear_extrude(width, center=false)
        
            circle(r=rail_radius+extra_radius, $fn=3);
        }
        translate([side*(length/2-bottom_thickness-vertical_rail_width/2), 
            width/2-bottom_thickness-1.2/2, 
           vertical_rail_height/2+bottom_thickness/2])        
        cube([vertical_rail_width, 1.2, vertical_rail_height], center=true);
    }
    //edge to support front
    translate([-length/2, 
        -width/2+bottom_thickness, 
        height-bottom_thickness+rail_radius])
    scale([1, 1, 1])
    rotate([0,90,0])
    linear_extrude(length, center=false)

    circle(r=rail_radius+extra_radius, $fn=3);
}

module pi4_holes_front() {
    //minijack
    color("white")
    translate([10.8,-width/2+bottom_thickness+0.1,8.4])
    rotate([90,0,0])    
    cylinder(h=bottom_thickness+0.2, r=5);
    
    //hdmi 1    
    color("white")
    translate([-10.05,-width/2+bottom_thickness+0.1,2.7])
    rotate([90,0,0])    
    cube([12.5, 9, bottom_thickness+0.2]);
    
    //hdmi 2  
    color("white")
    translate([-23.65,-width/2+bottom_thickness+0.1,2.7])
    rotate([90,0,0])    
    cube([12.5, 9, bottom_thickness+0.2]);
    
    //usb-c  
    color("white")
    translate([-39,-width/2+bottom_thickness+0.1,3])
    rotate([90,0,0])    
    cube([14, 8, bottom_thickness+0.2]);
    

     translate([0.8,0,1.25])
    union() {
        //right rca 
        union() {
            translate([7, -30, 25.7])
            rotate([90,0,0])
            cylinder(straight_hole_rim, 5.5, 5.5);   
            
            translate([7, -30 - straight_hole_rim, 25.7])
            rotate([90,0,0])
            cylinder(2.5-straight_hole_rim+0.1, 5.5, 5.5+extra);    
        }
        
        //left rca
        
        union() {
            translate([-10, -30, 25.7])
            rotate([90,0,0])
            cylinder(straight_hole_rim, 5.5, 5.5);   
            translate([-10, -30 - straight_hole_rim, 25.7])
            rotate([90,0,0])
            cylinder(2.5-straight_hole_rim+0.1, 5.5, 5.5+extra);
        
        }
        //minijack    
       union() {
           translate([-27.1, -30, 20])
            rotate([90,0,0])
            cylinder(straight_hole_rim, 4.5, 4.5);
            translate([-27.1, -30 - straight_hole_rim, 20])
            rotate([90,0,0])
            cylinder(2.5-straight_hole_rim+0.1, 4.5, 4.5+extra);
        }
    }
}

module pi4_holes_side() {
    //UTP
    color("white")
    translate([length/2-bottom_thickness/2,17.8,12.5])
    rotate([0,90,0])    
    cube([14.5,16.5, bottom_thickness+0.2], true);
    
    //USB 3
    color("white")
    translate([length/2-bottom_thickness/2,-19,14])
    rotate([0,90,0])    
    cube([16,15.5, bottom_thickness+0.2], true);
    
    //USB 3
    color("white")
    translate([length/2-bottom_thickness/2,-1,14])
    rotate([0,90,0])    
    cube([16,15.5, bottom_thickness+0.2], true);
    
}


module sd_card_slot() {
    translate([-length/2,0,0])
    intersection() {
        cube([16, 12, 10], center=true);

    }
}
