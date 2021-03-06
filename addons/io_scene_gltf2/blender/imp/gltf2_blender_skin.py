# Copyright 2018 The glTF-Blender-IO authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


import bpy
from mathutils import Vector, Matrix, Quaternion
from ..com.gltf2_blender_conversion import *
from ...io.imp.gltf2_io_binary import *

class BlenderSkin():

    @staticmethod
    def create_armature(gltf, skin_id, parent):

        pyskin = gltf.data.skins[skin_id]

        if pyskin.name is not None:
            name = pyskin.name
        else:
            name = "Armature_" + str(skin_id)

        armature = bpy.data.armatures.new(name)
        obj = bpy.data.objects.new(name, armature)
        bpy.data.scenes[gltf.blender_scene].objects.link(obj)
        pyskin.blender_armature_name = obj.name
        if parent is not None:
            obj.parent = bpy.data.objects[gltf.data.nodes[parent].blender_object]

    @staticmethod
    def set_bone_transforms(gltf, skin_id, bone, node_id, parent):

        pyskin = gltf.data.skins[skin_id]
        pynode = gltf.data.nodes[node_id]

        obj   = bpy.data.objects[pyskin.blender_armature_name]

        mat = Matrix()
        if parent is None:
            transform = Conversion.matrix_gltf_to_blender(pynode.transform)
            mat = transform
        else:
            if not gltf.data.nodes[parent].is_joint:
                transform  = Conversion.matrix_gltf_to_blender(pynode.transform)
                mat = transform
            else:
                transform = Conversion.matrix_gltf_to_blender(pynode.transform)
                parent_mat = obj.data.edit_bones[gltf.data.nodes[parent].blender_bone_name].matrix

                mat = (parent_mat.to_quaternion() * transform.to_quaternion()).to_matrix().to_4x4()
                mat = Matrix.Translation(parent_mat.to_translation() + ( parent_mat.to_quaternion() * transform.to_translation() )) * mat
                #TODO scaling of bones ?

        bone.matrix = mat
        return bone.matrix

    @staticmethod
    def create_bone(gltf, skin_id, node_id, parent):

        pyskin = gltf.data.skins[skin_id]
        pynode = gltf.data.nodes[node_id]

        scene = bpy.data.scenes[gltf.blender_scene]
        obj   = bpy.data.objects[pyskin.blender_armature_name]

        bpy.context.screen.scene = scene
        scene.objects.active = obj
        bpy.ops.object.mode_set(mode="EDIT")

        if pynode.name:
            name = pynode.name
        else:
            name = "Bone_" + str(node_id)

        bone = obj.data.edit_bones.new(name)
        pynode.blender_bone_name = bone.name
        pynode.blender_armature_name = pyskin.blender_armature_name
        bone.tail = Vector((0.0,1.0,0.0)) # Needed to keep bone alive
        mat = BlenderSkin.set_bone_transforms(gltf, skin_id, bone, node_id, parent)
        pynode.blender_bone_matrix = mat

        # Set parent
        if parent is not None and hasattr(gltf.data.nodes[parent], "blender_bone_name"):
            bone.parent = obj.data.edit_bones[gltf.data.nodes[parent].blender_bone_name]

        bpy.ops.object.mode_set(mode="OBJECT")

    @staticmethod
    def create_vertex_groups(gltf, skin_id):
        pyskin = gltf.data.skins[skin_id]
        if not hasattr(pyskin, "node_id"): # some skin can be not used
            return
        obj = bpy.data.objects[gltf.data.nodes[pyskin.node_id].blender_object]
        for bone in pyskin.joints:
            obj.vertex_groups.new(gltf.data.nodes[bone].blender_bone_name)

    @staticmethod
    def assign_vertex_groups(gltf, skin_id):
        pyskin = gltf.data.skins[skin_id]
        if not hasattr(pyskin, "node_id"): # some skin can be not used
            return
        node = gltf.data.nodes[pyskin.node_id]
        obj = bpy.data.objects[node.blender_object]

        offset = 0
        for prim in gltf.data.meshes[node.mesh].primitives:
            idx_already_done = {}

            if 'JOINTS_0' in prim.attributes.keys() and 'WEIGHTS_0' in prim.attributes.keys():
                joint_ = BinaryData.get_data_from_accessor(gltf, prim.attributes['JOINTS_0'])
                weight_ = BinaryData.get_data_from_accessor(gltf, prim.attributes['WEIGHTS_0'])

                for poly in obj.data.polygons:
                    for loop_idx in range(poly.loop_start, poly.loop_start + poly.loop_total):
                        vert_idx = obj.data.loops[loop_idx].vertex_index

                        if vert_idx in idx_already_done.keys():
                            continue
                        idx_already_done[vert_idx] = True

                        if vert_idx in range(offset, offset + prim.vertices_length):

                            tab_index = vert_idx - offset
                            cpt = 0
                            for joint_idx in joint_[tab_index]:
                                weight_val = weight_[tab_index][cpt]
                                if weight_val != 0.0:   # It can be a problem to assign weights of 0
                                                        # for bone index 0, if there is always 4 indices in joint_ tuple
                                    group = obj.vertex_groups[gltf.data.nodes[pyskin.joints[joint_idx]].blender_bone_name]
                                    group.add([vert_idx], weight_val, 'REPLACE')
                                cpt += 1
            else:
                pyskin.gltf.log.error("No Skinning ?????") #TODO


            offset = offset + prim.vertices_length

    @staticmethod
    def create_armature_modifiers(gltf, skin_id):

        pyskin = gltf.data.skins[skin_id]

        if pyskin.blender_armature_name is None:
            # TODO seems something is wrong
            # For example, some joints are in skin 0, and are in another skin too
            # Not sure this is glTF compliant, will check it
            return


        node = gltf.data.nodes[pyskin.node_id]
        obj = bpy.data.objects[node.blender_object]

        for obj_sel in bpy.context.scene.objects:
            obj_sel.select = False
        obj.select = True
        bpy.context.scene.objects.active = obj

        #bpy.ops.object.parent_clear(type='CLEAR_KEEP_TRANSFORM')
        #obj.parent = bpy.data.objects[pyskin.blender_armature_name]
        arma = obj.modifiers.new(name="Armature", type="ARMATURE")
        arma.object = bpy.data.objects[pyskin.blender_armature_name]
