# MIT License

# Copyright (c) 2018-2024 Nathan Letwory, Joel Putnam, Tom Svilans, Lukas Fertig

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import rhino3dm as r3d
from . import utils


def handle_layers(context, model, toplayer, layerids, materials, update, import_hidden=False):
    """
    In context read the Rhino layers from model
    then update the layerids dictionary passed in.
    Update materials dictionary with materials created
    for layer color.

    Returns a dict mapping collection_name -> dict(effective_visible=bool, own_visible=bool).
    """
    layer_dict = {str(l.Id): l for l in model.Layers}

    def is_effective_visible(l):
        curr = l
        while curr:
            if not curr.Visible:
                return False
            parent_id = str(curr.ParentLayerId)
            if parent_id in layer_dict:
                curr = layer_dict[parent_id]
            else:
                break
        return True

    layer_visibility = {}

    # Setup main container to hold layer collections SPECIFIC to this imported file
    layer_col_name = f"Layers ({toplayer.name})"
    layer_col = toplayer.children.get(layer_col_name)
    if not layer_col:
        layer_col = context.blend_data.collections.new(name=layer_col_name)
        try:
            toplayer.children.link(layer_col)
        except Exception:
            pass

    # Build lookup table for LayerTable index
    layer_name_counts = {}
    for l in model.Layers:
        layer_name_counts[l.Name] = layer_name_counts.get(l.Name, 0) + 1

    for lid, l in enumerate(model.Layers):
        # Scope collection creation to this imported file to avoid cross-file collection collisions
        col_name = l.FullPath if (layer_name_counts.get(l.Name, 0) > 1 and hasattr(l, "FullPath") and l.FullPath) else l.Name
        
        # Look for existing collection under layer_col
        lcol = layer_col.children.get(col_name)
        if not lcol:
            tags = utils.create_tag_dict(l.Id, col_name)
            lcol = context.blend_data.collections.new(name=col_name)
            utils.tag_data(lcol, tags)

        lcol["rhid"] = str(l.Id)
        lcol["rhino_full_path"] = str(l.FullPath)
        lcol["rhino_layer_name"] = str(l.Name)
        lcol["rhino_own_visible"] = l.Visible

        layerids[str(l.Id)] = lcol
        layerids[lid] = lcol
        layerids[l.Index] = lcol

        layer_visibility[lcol.name] = {
            "effective_visible": is_effective_visible(l),
            "own_visible": l.Visible,
            "layer_index": lid
        }

    # Second pass: link layers cleanly into layer_col hierarchy for this file
    for l in model.Layers:
        if str(l.Id) not in layerids:
            continue
        child_col = layerids[str(l.Id)]
        
        # Link up layers to their parent layers
        if str(l.ParentLayerId) in layerids:
            parentlayer = layerids[str(l.ParentLayerId)]
            if child_col.name in layer_col.children:
                try:
                    layer_col.children.unlink(child_col)
                except Exception:
                    pass
            if child_col.name not in parentlayer.children:
                try:
                    parentlayer.children.link(child_col)
                except Exception:
                    pass
        else:
            if child_col.name not in layer_col.children:
                try:
                    layer_col.children.link(child_col)
                except Exception:
                    pass

    return layer_visibility
