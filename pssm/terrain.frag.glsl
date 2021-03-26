#version 330

// Number of splits in the PSSM, it must be in line with what is configured in the PSSMCameraRig
const int split_count = 5;

uniform mat3 p3d_NormalMatrix;

uniform struct {
  sampler2D data_texture;
  sampler2D heightfield;
  int view_index;
  int terrain_size;
  int chunk_size;
} ShaderTerrainMesh;

uniform struct {
  vec4 position;
  vec3 color;
  vec3 attenuation;
  vec3 spotDirection;
  float spotCosCutoff;
  float spotExponent;
  sampler2DShadow shadowMap;
  mat4 shadowViewMatrix;
} p3d_LightSource[1];

uniform struct {
  vec4 ambient;
} p3d_LightModel;

uniform sampler2D p3d_Texture0;
uniform vec3 wspos_camera;

uniform sampler2D PSSMShadowAtlas;

uniform mat4 pssm_mvps[split_count];
uniform vec2 pssm_nearfar[split_count];
uniform float border_bias;
uniform float fixed_bias;
uniform bool use_pssm;
uniform bool fog;

in vec2 terrain_uv;
in vec3 vtx_pos;
in vec4 projecteds[1];

out vec4 color;

// Compute normal from the heightmap, this assumes the terrain is facing z-up
vec3 get_terrain_normal() {
  const float terrain_height = 50.0;
  vec3 pixel_size = vec3(1.0, -1.0, 0) / textureSize(ShaderTerrainMesh.heightfield, 0).xxx;
  float u0 = texture(ShaderTerrainMesh.heightfield, terrain_uv + pixel_size.yz).x * terrain_height;
  float u1 = texture(ShaderTerrainMesh.heightfield, terrain_uv + pixel_size.xz).x * terrain_height;
  float v0 = texture(ShaderTerrainMesh.heightfield, terrain_uv + pixel_size.zy).x * terrain_height;
  float v1 = texture(ShaderTerrainMesh.heightfield, terrain_uv + pixel_size.zx).x * terrain_height;
  vec3 tangent = normalize(vec3(1.0, 0, u1 - u0));
  vec3 binormal = normalize(vec3(0, 1.0, v1 - v0));
  return normalize(cross(tangent, binormal));
}

// Projects a point using the given mvp
vec3 project(mat4 mvp, vec3 p) {
    vec4 projected = mvp * vec4(p, 1);
    return (projected.xyz / projected.w) * vec3(0.5) + vec3(0.5);
}

void main() {
  vec3 diffuse = texture(p3d_Texture0, terrain_uv * 16.0).xyz;
  vec3 normal = normalize(p3d_NormalMatrix * get_terrain_normal());
 
  vec3 shading = vec3(0.0);

  // Calculate the shading of each light in the scene
  for (int i = 0; i < p3d_LightSource.length(); ++i) {
    vec3 diff = p3d_LightSource[i].position.xyz - vtx_pos * p3d_LightSource[i].position.w;
    vec3 light_vector = normalize(diff);
    vec3 light_shading = clamp(dot(normal, light_vector), 0.0, 1.0) * p3d_LightSource[i].color;
    // If PSSM is not used, use the shadowmap from the light
    // This is deeply ineficient, it's only to be able to compare the rendered shadows
    if (!use_pssm) {
      vec4 projected = projecteds[i];
      // Apply a bias to remove some of the self-shadow acne
      projected.z -= fixed_bias * 0.01 * projected.w;
      light_shading *= textureProj(p3d_LightSource[i].shadowMap, projected);
    }
    shading += light_shading;
  }

  if (use_pssm) {
    // Find in which split the current point is present.
    int split = 99;
    float border_bias = 0.5 - (0.5 / (1.0 + border_bias));
 
    // Find the first matching split
    for (int i = 0; i < split_count; ++i) {
        vec3 coord = project(pssm_mvps[i], vtx_pos);
        if (coord.x >= border_bias && coord.x <= 1 - border_bias &&
            coord.y >= border_bias && coord.y <= 1 - border_bias &&
            coord.z >= 0.0 && coord.z <= 1.0) {
            split = i;
            break;
        }
    }
 
    // Compute the shadowing factor
    if (split < split_count) {
 
        // Get the MVP for the current split
        mat4 mvp = pssm_mvps[split];
 
        // Project the current pixel to the view of the light
        vec3 projected = project(mvp, vtx_pos);
        vec2 projected_coord = vec2((projected.x + split) / float(split_count), projected.y);
        // Apply a fixed bias based on the current split to diminish the shadow acne
        float ref_depth = projected.z - fixed_bias * 0.001 * (1 + 1.5 * split);
 
        // Check if the pixel is shadowed or not
        float depth_sample = textureLod(PSSMShadowAtlas, projected_coord, 0).x;
        float shadow_factor = step(ref_depth, depth_sample);
 
        shading *= shadow_factor;
    }
  }

  shading += p3d_LightModel.ambient.xyz;

  shading *= diffuse;

  if (fog) {
    // Fake fog
    float dist = distance(vtx_pos, wspos_camera);
    float fog_factor = smoothstep(0, 1, dist / 2000.0);
    shading = mix(shading, vec3(0.7, 0.7, 0.8), fog_factor);
  }

  color = vec4(shading, 1.0);
}
