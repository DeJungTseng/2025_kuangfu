import xml.etree.ElementTree as ET
import json
import unicodedata
import re
import os
import shutil

def kml_color_to_hex(kml_color):
    """
    Converts a KML color string (aabbggrr) to a standard web hex color (#RRGGBB).
    """
    if not kml_color or len(kml_color) != 8:
        return None
    
    # KML format is aabbggrr (alpha, blue, green, red)
    # Reorder and format to standard #rrggbb
    red = kml_color[6:8]
    green = kml_color[4:6]
    blue = kml_color[2:4]
    
    return f'#{red}{green}{blue}'.upper()

def parse_kml_styles(root, ns):
    """
    Parses <Style> and <StyleMap> elements and returns a lookup dictionary 
    mapping style URLs to icon and color properties.
    """
    style_map = {}
    
    # 1. Parse individual <Style> definitions
    for style in root.findall(f'.//{ns}Style'):
        style_id = style.get('id')
        if not style_id:
            continue
            
        details = {'icon': None, 'color': None}
        
        # Extract Icon URL
        icon_href = style.find(f'{ns}IconStyle/{ns}Icon/{ns}href')
        if icon_href is not None and icon_href.text:
            details['icon'] = icon_href.text.strip()

        # Extract Color (prioritize IconStyle color for points)
        color_element = style.find(f'{ns}IconStyle/{ns}color')
        if color_element is None:
            # Check for Line/Poly style color as fallback
            color_element = style.find(f'{ns}LineStyle/{ns}color') or style.find(f'{ns}PolyStyle/{ns}color')

        if color_element is not None and color_element.text:
            details['color'] = kml_color_to_hex(color_element.text.strip())

        style_map[f'#{style_id}'] = details

    # 2. Parse <StyleMap> definitions (maps a map ID to a Style ID)
    # This assumes 'normal' style is the one we want to use
    for style_map_element in root.findall(f'.//{ns}StyleMap'):
        map_id = style_map_element.get('id')
        if not map_id:
            continue
            
        normal_pair = style_map_element.find(f'{ns}Pair[{ns}key="normal"]/{ns}styleUrl')
        
        if normal_pair is not None and normal_pair.text:
            style_map[f'#{map_id}'] = style_map.get(normal_pair.text.strip(), {'icon': None, 'color': None})

    return style_map

def extract_placemark_data(file_path):
    """
    Parses a KML file and extracts detailed information from each placemark,
    including name, description, geometry, coordinates, icon, and color.
    """
    try:
        tree = ET.parse(file_path)
    except ET.ParseError:
        # Fallback for parsing if ET.parse fails (e.g., non-standard characters)
        with open(file_path, 'r', encoding='utf-8') as f:
            xml_content = f.read()
        xml_content = "".join(ch for ch in xml_content if unicodedata.category(ch)[0] != 'C' or ch in ('\t', '\n', '\r'))
        try:
            root = ET.fromstring(xml_content)
        except ET.ParseError as e:
            print(f"Failed to parse KML even after cleaning: {e}")
            return []
    except FileNotFoundError as e:
        print(f"Error: {e}. Please ensure the KML file is in the same directory.")
        return []
    else:
        root = tree.getroot()

    placemarks_data = []
    ns = '{http://www.opengis.net/kml/2.2}'
    
    # NEW: Parse all styles first
    style_lookup = parse_kml_styles(root, ns)

    for placemark in root.findall(f'.//{ns}Placemark'):
        name_element = placemark.find(f'{ns}name')
        name = name_element.text.strip() if name_element is not None and name_element.text else 'No Name'

        description_element = placemark.find(f'{ns}description')
        description = description_element.text.strip() if description_element is not None and description_element.text else 'No Description'

        # Get Style/Icon/Color details
        style_url_element = placemark.find(f'{ns}styleUrl')
        style_url = style_url_element.text.strip() if style_url_element is not None and style_url_element.text else None
        
        style_details = style_lookup.get(style_url, {'icon': None, 'color': None})
        
        # --- Geometry Extraction (kept the same) ---
        point = placemark.find(f'.//{ns}Point')
        linestring = placemark.find(f'.//{ns}LineString')
        polygon = placemark.find(f'.//{ns}Polygon')

        geom_type = 'Unknown'
        coordinates_text = None

        if point is not None:
            geom_type = 'Point'
            coordinates_element = point.find(f'.//{ns}coordinates')
            if coordinates_element is not None:
                coordinates_text = coordinates_element.text
        elif linestring is not None:
            geom_type = 'LineString'
            coordinates_element = linestring.find(f'.//{ns}coordinates')
            if coordinates_element is not None:
                coordinates_text = coordinates_element.text
        elif polygon is not None:
            geom_type = 'Polygon'
            coordinates_element = polygon.find(f'.//{ns}LinearRing/{ns}coordinates')
            if coordinates_element is not None:
                coordinates_text = coordinates_element.text

        coords = []
        if coordinates_text:
            coord_tuples = re.findall(r'(-?\d+\.\d+),(-?\d+\.\d+)(?:,-?\d+\.?\d*)?', coordinates_text.strip())
            for lon_str, lat_str in coord_tuples:
                try:
                    lon = float(lon_str)
                    lat = float(lat_str)
                    coords.append([lon, lat])
                except ValueError:
                    continue
        
        if coords: # Only add placemarks that have coordinates
            placemarks_data.append({
                'name': name,
                'description': description,
                'type': geom_type,
                'coordinates': coords,
                # NEW PROPERTIES
                'color': style_details['color'], 
                'icon': style_details['icon']
            })

    return placemarks_data

if __name__ == '__main__':
    # File name the script expects
    kml_file = 'outputs/downloaded/8_lin_map.kml' 
    # File name that was uploaded
    actual_kml_file = '光復鄉-救災資訊整合.kml' 
    output_filename = 'outputs/spatial_info_json/8_spatial_info.json'

    # --- FIX THE FILE NAME ISSUE HERE (Kept from previous fix) ---
    if not os.path.exists(kml_file) and os.path.exists(actual_kml_file):
        print(f"File '{kml_file}' not found. Copying '{actual_kml_file}' to it.")
        try:
            shutil.copyfile(actual_kml_file, kml_file)
        except Exception as e:
            print(f"Error copying file: {e}. Ensure both files are accessible.")
    # -----------------------------------

    placemark_details = extract_placemark_data(kml_file)

    if placemark_details:
        with open(output_filename, 'w', encoding='utf-8') as f:
            json.dump(placemark_details, f, indent=2, ensure_ascii=False)
        print(f"Successfully extracted and saved details for {len(placemark_details)} placemarks to {output_filename}.")
    else:
        print("No placemarks with coordinates found, or the KML file could not be parsed.")