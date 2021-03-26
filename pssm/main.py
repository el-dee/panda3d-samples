#!/usr/bin/env python

# This tutorial provides an example of using the PSSMCameraRig
# This is based on the ShaderTerrainMesh sample and RenderPipeline made by tobspr#

from direct.showbase.ShowBase import ShowBase
from panda3d.core import ShaderTerrainMesh, Shader, load_prc_file_data
from panda3d.core import AmbientLight, DirectionalLight

from panda3d.core import SamplerState, Texture
from panda3d.core import WindowProperties, FrameBufferProperties, GraphicsPipe, GraphicsOutput

from panda3d._rplight import PSSMCameraRig

class ShaderTerrainDemo(ShowBase):
    def __init__(self):

        # Load some configuration variables, its important for this to happen
        # before the ShowBase is initialized
        load_prc_file_data("", """
            textures-power-2 none
            gl-coordinate-system default
            window-title Panda3D PSSM Demo
            gl-version 3 2
            framebuffer-srgb true
        """)

        # Initialize the showbase
        ShowBase.__init__(self)

        self.camera_rig = None
        self.split_regions = []

        # Basic PSSM configuration
        self.num_splits = 5
        self.split_resolution = 1024
        self.border_bias = 0.058
        self.fixed_bias = 0.5
        self.use_pssm = True
        self.freeze_pssm = False
        self.fog = True
        self.last_cache_reset = globalClock.get_frame_time()

        # Increase camera FOV as well as the far plane
        self.camLens.set_fov(90)
        self.camLens.set_near_far(0.1, 50000)

        # Construct the terrain
        self.terrain_node = ShaderTerrainMesh()

        # Set a heightfield, the heightfield should be a 16-bit png and
        # have a quadratic size of a power of two.
        heightfield = self.loader.loadTexture("heightfield.png")
        heightfield.wrap_u = SamplerState.WM_clamp
        heightfield.wrap_v = SamplerState.WM_clamp
        self.terrain_node.heightfield = heightfield

        # Set the target triangle width. For a value of 10.0 for example,
        # the terrain will attempt to make every triangle 10 pixels wide on screen.
        self.terrain_node.target_triangle_width = 10.0

        # Generate the terrain
        self.terrain_node.generate()

        # Attach the terrain to the main scene and set its scale. With no scale
        # set, the terrain ranges from (0, 0, 0) to (1, 1, 1)
        self.terrain = self.render.attach_new_node(self.terrain_node)
        self.terrain.set_scale(1024, 1024, 100)
        self.terrain.set_pos(-512, -512, -70.0)

        # Set a shader on the terrain. The ShaderTerrainMesh only works with
        # an applied shader. You can use the shaders used here in your own application
        terrain_shader = Shader.load(Shader.SL_GLSL, "terrain.vert.glsl", "terrain.frag.glsl")
        self.terrain.set_shader(terrain_shader)
        self.terrain.set_shader_input("camera", self.camera)

        # Shortcuts to configure the scene
        self.accept("escape", self.userExit)
        self.accept("f3", self.toggleWireframe)
        self.accept("f5", self.bufferViewer.toggleEnable)
        self.accept("s", self.toggle_shadows_mode)
        self.accept("f", self.toggle_freeze_pssm)
        self.accept("g", self.toggle_fog)

        # Set some texture on the terrain
        grass_tex = self.loader.loadTexture("textures/grass.png")
        grass_tex.set_format(Texture.F_srgb_alpha)
        grass_tex.set_minfilter(SamplerState.FT_linear_mipmap_linear)
        grass_tex.set_anisotropic_degree(16)
        self.terrain.set_texture(grass_tex)

        # Load a trivial skybox
        skybox = self.loader.loadModel("models/skybox.bam")
        skybox.reparent_to(self.render)
        skybox.set_scale(20000)

        skybox_texture = self.loader.loadTexture("textures/skybox.jpg")
        skybox_texture.set_format(Texture.F_srgb)
        skybox_texture.set_minfilter(SamplerState.FT_linear)
        skybox_texture.set_magfilter(SamplerState.FT_linear)
        skybox_texture.set_wrap_u(SamplerState.WM_repeat)
        skybox_texture.set_wrap_v(SamplerState.WM_mirror)
        skybox_texture.set_anisotropic_degree(16)
        skybox.set_texture(skybox_texture)

        skybox_shader = Shader.load(Shader.SL_GLSL, "skybox.vert.glsl", "skybox.frag.glsl")
        skybox.set_shader(skybox_shader)

        # Create ambient lighting
        self.ambient_light = AmbientLight("ambient_light")
        self.ambient_light.set_color((.18, .18, .18, 1))
        self.ambient_light_path = self.render.attach_new_node(self.ambient_light)

        # Create directional light, representing the Sun
        self.directional_light = DirectionalLight("directional_light")
        self.directional_light.set_color_temperature(6000)
        self.directional_light_path = self.render.attach_new_node(self.directional_light)
        self.directional_light_path.set_pos(512, 512, 256)
        self.directional_light_path.look_at(0, 0, 0)

        # Configure the directional light to cast shadows
        self.directional_light.set_shadow_caster(True, 1024, 1024)
        self.directional_light.get_lens().set_near_far(0, 1024)
        self.directional_light.get_lens().set_film_size(1024, 1024)
        #self.directional_light.show_frustum()

        self.render.set_light(self.ambient_light_path)
        self.render.set_light(self.directional_light_path)

        # Create the PSSM
        self.create_pssm_camera_rig()
        self.create_pssm_buffer()
        self.attach_pssm_camera_rig()
        self.set_shader_inputs(self.terrain)

        # Start the task that will periodically update the PSSM configuration
        self.task_mgr.add(self.update)

    def toggle_shadows_mode(self):
        self.use_pssm = not self.use_pssm
        self.terrain.set_shader_inputs(use_pssm=self.use_pssm)

    def toggle_freeze_pssm(self):
        self.freeze_pssm = not self.freeze_pssm

    def toggle_fog(self):
        self.fog = not self.fog
        self.terrain.set_shader_inputs(fog=self.fog)

    def update(self, task):
        if not self.freeze_pssm:
            # Update the camera position and the light direction
            light_dir = self.directional_light_path.get_mat().xform(-self.directional_light.get_direction()).xyz
            self.camera_rig.update(self.camera, light_dir)
        cache_diff = globalClock.get_frame_time() - self.last_cache_reset
        if cache_diff > 5.0:
            self.last_cache_reset = globalClock.get_frame_time()
            self.camera_rig.reset_film_size_cache()
        return task.cont

    def create_pssm_camera_rig(self):
        # Construct the actual PSSM rig
        self.camera_rig = PSSMCameraRig(self.num_splits)
        # Set the max distance from the camera where shadows are rendered
        self.camera_rig.set_pssm_distance(2048)
        # Set the distance between the far plane of the frustum and the sun, objects farther do not cas shadows
        self.camera_rig.set_sun_distance(1024)
        # Set the logarithmic factor that defines the splits
        self.camera_rig.set_logarithmic_factor(2.4)
        
        self.camera_rig.set_border_bias(self.border_bias)
        # Enable CSM splits snapping to avoid shadows flickering when moving
        self.camera_rig.set_use_stable_csm(True)
        # Keep the film size roughly constant to avoid flickering when moving
        self.camera_rig.set_use_fixed_film_size(True)
        # Set the resolution of each split shadow map
        self.camera_rig.set_resolution(self.split_resolution)
        self.camera_rig.reparent_to(self.render)

    def create_pssm_buffer(self):
        # Create the depth buffer
        # The depth buffer is the concatenation of num_splits shadow maps
        self.depth_tex = Texture("PSSMShadowMap")
        self.buffer = self.create_render_buffer(
            self.split_resolution * self.num_splits, self.split_resolution,
            32,
            self.depth_tex)

        # Remove all unused display regions
        self.buffer.remove_all_display_regions()
        self.buffer.get_display_region(0).set_active(False)
        self.buffer.disable_clears()

        # Set a clear on the buffer instead on all regions
        self.buffer.set_clear_depth(1)
        self.buffer.set_clear_depth_active(True)

        # Prepare the display regions, one for each split
        for i in range(self.num_splits):
            region = self.buffer.make_display_region(
                i / self.num_splits,
                i / self.num_splits + 1 / self.num_splits, 0, 1)
            region.set_sort(25 + i)
            # Clears are done on the buffer
            region.disable_clears()
            region.set_active(True)
            self.split_regions.append(region)

    def attach_pssm_camera_rig(self):
        # Attach the cameras to the shadow stage
        for i in range(5):
            camera_np = self.camera_rig.get_camera(i)
            camera_np.node().set_scene(self.render)
            self.split_regions[i].set_camera(camera_np)

    def set_shader_inputs(self, target):
        # Configure the parameters for the PSSM Shader
        target.set_shader_inputs(PSSMShadowAtlas=self.depth_tex,
                                 pssm_mvps=self.camera_rig.get_mvp_array(),
                                 pssm_nearfar=self.camera_rig.get_nearfar_array(),
                                 border_bias=self.border_bias,
                                 fixed_bias=self.fixed_bias,
                                 use_pssm=self.use_pssm,
                                 fog=self.fog)

    def create_render_buffer(self, size_x, size_y, depth_bits, depth_tex):
        # Boilerplate code to create a render buffer producing only a depth texture
        window_props = WindowProperties.size(size_x, size_y)
        buffer_props = FrameBufferProperties()

        buffer_props.set_rgba_bits(0, 0, 0, 0)
        buffer_props.set_accum_bits(0)
        buffer_props.set_stencil_bits(0)
        buffer_props.set_back_buffers(0)
        buffer_props.set_coverage_samples(0)
        buffer_props.set_depth_bits(depth_bits)

        if depth_bits == 32:
            buffer_props.set_float_depth(True)

        buffer_props.set_force_hardware(True)
        buffer_props.set_multisamples(0)
        buffer_props.set_srgb_color(False)
        buffer_props.set_stereo(False)
        buffer_props.set_stencil_bits(0)

        buffer = self.graphics_engine.make_output(
            self.win.get_pipe(), "pssm_buffer", 1,
            buffer_props, window_props, GraphicsPipe.BF_refuse_window,
            self.win.gsg, self.win)

        if buffer is None:
            print("Failed to create buffer")
            return

        buffer.add_render_texture(
            self.depth_tex, GraphicsOutput.RTM_bind_or_copy,
            GraphicsOutput.RTP_depth)

        buffer.set_sort(-1000)
        buffer.disable_clears()
        buffer.get_display_region(0).disable_clears()
        buffer.get_overlay_display_region().disable_clears()
        buffer.get_overlay_display_region().set_active(False)

        return buffer

ShaderTerrainDemo().run()
