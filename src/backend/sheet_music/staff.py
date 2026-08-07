import xml.etree.ElementTree as ET


def notes_to_musicxml(tracks, bpm, output_path):
    """Create a minimal MusicXML file from the note tracks."""
    root = ET.Element("score-partwise", version="3.1")
    part_list = ET.SubElement(root, "part-list")

    for idx, (name, notes) in enumerate(tracks.items(), 1):
        score_part = ET.SubElement(part_list, "score-part", id=f"P{idx}")
        ET.SubElement(score_part, "part-name").text = name

    for idx, (name, notes) in enumerate(tracks.items(), 1):
        part = ET.SubElement(root, "part", id=f"P{idx}")
        measure = ET.SubElement(part, "measure", number="1")
        attrs = ET.SubElement(measure, "attributes")
        ET.SubElement(attrs, "divisions").text = "4"
        time = ET.SubElement(attrs, "time")
        ET.SubElement(time, "beats").text = "4"
        ET.SubElement(time, "beat-type").text = "4"
        key = ET.SubElement(attrs, "key")
        ET.SubElement(key, "fifths").text = "0"
        clef = ET.SubElement(attrs, "clef")
        ET.SubElement(clef, "sign").text = "G" if "guitar" in name.lower() or name == "Guitar" else "F"
        ET.SubElement(clef, "line").text = "2" if "guitar" in name.lower() or name == "Guitar" else "4"

        direction = ET.SubElement(measure, "direction", placement="above")
        direction_type = ET.SubElement(direction, "direction-type")
        metronome = ET.SubElement(direction_type, "metronome")
        ET.SubElement(metronome, "beat-unit").text = "quarter"
        ET.SubElement(metronome, "per-minute").text = str(int(bpm))

        for n in sorted(notes, key=lambda x: x["start"]):
            note_el = ET.SubElement(measure, "note")
            ET.SubElement(note_el, "pitch")
            ET.SubElement(note_el.find("pitch"), "step").text = midi_step(n["pitch"])
            ET.SubElement(note_el.find("pitch"), "octave").text = str(n["pitch"] // 12 - 1)
            ET.SubElement(note_el, "duration").text = str(max(1, int(round((n["end"] - n["start"]) * 4))))
            ET.SubElement(note_el, "type").text = "quarter"
            ET.SubElement(note_el, "voice").text = "1"

    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ", level=0)
    tree.write(output_path, encoding="utf-8", xml_declaration=True)
    return output_path


def midi_step(midi):
    steps = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]
    return steps[midi % 12]
