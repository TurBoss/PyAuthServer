from network.decorators import requires_netmode, simulated
from network.descriptors import Attribute
from network.enums import Netmodes, Roles
from network.replicable import Replicable
from network.signals import UpdateSignal
from network.world_info import WorldInfo

from aud import Factory, device as Device
from bge import logic, types
from contextlib import contextmanager
from math import radians
from mathutils import Vector, Euler

from .behaviour_tree import BehaviourTree
from .enums import *
from .object_types import *
from .physics_object import PhysicsObject
from .signals import *
from .structs import RigidBodyState


__all__ = ["Actor", "Camera", "Lamp", "Navmesh", "Pawn", "ResourceActor",
           "WeaponAttachment"]


class Actor(Replicable, PhysicsObject):
    '''Physics enabled network object'''

    rigid_body_state = Attribute(RigidBodyState(), notify=True)
    roles = Attribute(Roles(Roles.authority, Roles.simulated_proxy),
                    notify=True)

    def conditions(self, is_owner, is_complaint, is_initial):
        yield from super().conditions(is_owner, is_complaint, is_initial)

        remote_role = self.roles.remote

        # If simulated, send rigid body state
        valid_role = ((remote_role == Roles.simulated_proxy) or
                     (remote_role == Roles.autonomous_proxy and not is_owner))
        allowed_physics = ((self.replicate_simulated_physics or is_initial)
                        and (self.replicate_physics_to_owner or not is_owner))

        if valid_role and allowed_physics:
            yield "rigid_body_state"

    def on_initialised(self):
        super().on_initialised()

        self.camera_radius = 1

        self.always_relevant = False
        self.replicate_physics_to_owner = True
        self.replicate_simulated_physics = True

    def on_unregistered(self):
        # Unregister any actor children
        for child in self.children:
            if isinstance(child, ResourceActor):
                continue

            child.request_unregistration()

        super().on_unregistered()

    def on_notify(self, name):
        if name == "rigid_body_state":
            PhysicsReplicatedSignal.invoke(self.rigid_body_state, target=self)
        else:
            super().on_notify(name)

    @simulated
    def trace_ray(self, local_vector):
        target = self.transform * local_vector

        return self.object.rayCast(self.object, target)

    @simulated
    def align_to(self, vector, time=1, axis=Axis.y):
        if not vector.length:
            return
        self.object.alignAxisToVect(vector, axis, time)


class ResourceActor(Actor):
    pass


class Camera(Actor):

    entity_class = CameraObject
    entity_name = "Camera"

    roles = Attribute(Roles(Roles.authority, Roles.autonomous_proxy),
                    notify=True)

    @property
    def active(self):
        return self.object == logic.getCurrentScene().active_camera

    @active.setter
    def active(self, status):
        if status:
            logic.getCurrentScene().active_camera = self.object

    @property
    def lens(self):
        return self.object.lens

    @lens.setter
    def lens(self, value):
        self.object.lens = value

    @property
    def fov(self):
        return self.object.fov

    @fov.setter
    def fov(self, value):
        self.object.fov = value

    @property
    def mode(self):
        return self._mode

    @mode.setter
    def mode(self, mode):
        if mode == self._mode:
            return

        if mode == CameraMode.first_person:
            self.local_position = Vector()

        else:
            self.local_position = Vector((0, -self.gimbal_offset, 0))

        self.local_rotation = Euler()
        self._mode = mode

    @property
    def rotation(self):
        rotation = Euler((-radians(90), 0, 0))
        rotation.rotate(self.object.worldOrientation)
        return rotation

    @rotation.setter
    def rotation(self, rot):
        rotation = Euler((radians(90), 0, 0))
        rotation.rotate(rot)
        self.object.worldOrientation = rotation

    @property
    def local_rotation(self):
        rotation = Euler((-radians(90), 0, 0))
        rotation.rotate(self.object.localOrientation)
        return rotation

    @local_rotation.setter
    def local_rotation(self, rot):
        rotation = Euler((radians(90), 0, 0))
        rotation.rotate(rot)
        self.object.localOrientation = rotation

    @contextmanager
    def active_context(self):
        cam = self.object
        scene = cam.scene

        old_camera = scene.active_camera
        scene.active_camera = cam
        yield
        if old_camera:
            scene.active_camera = old_camera

    def draw(self):
        '''Draws a colourful 3D camera object to the screen'''
        orientation = self.rotation.to_matrix()
        circle_size = 0.20
        upwards_orientation = orientation * Matrix.Rotation(radians(90),
                                                            3, "X")
        upwards_vector = Vector(upwards_orientation.col[1])

        sideways_orientation = orientation * Matrix.Rotation(radians(-90),
                                                            3, "Z")
        sideways_vector = (Vector(sideways_orientation.col[1]))
        forwards_vector = Vector(orientation.col[1])

        draw_arrow(self.position, orientation, colour=[0, 1, 0])
        draw_arrow(self.position + upwards_vector * circle_size,
                upwards_orientation, colour=[0, 0, 1])
        draw_arrow(self.position + sideways_vector * circle_size,
                sideways_orientation, colour=[1, 0, 0])
        draw_circle(self.position, orientation, circle_size)
        draw_box(self.position, orientation)
        draw_square_pyramid(self.position + forwards_vector * 0.4, orientation,
                            colour=[1, 1, 0], angle=self.fov, incline=False)

    def on_initialised(self):
        super().on_initialised()

        self._mode = None

        self.gimbal_offset = 2.0
        self.mode = CameraMode.first_person

    def sees_actor(self, actor):
        '''Determines if actor is visible to camera

        :param actor: Actor subclass
        :returns: condition result'''
        try:
            radius = actor.camera_radius
        except AttributeError:
            radius = 0.0

        if radius < 0.5:
            return self.object.pointInsideFrustum(actor.position)

        return self.object.sphereInsideFrustum(actor.position, radius) != self.object.OUTSIDE

    def trace(self, x_coord, y_coord, distance=0):
        return self.object.getScreenRay(x_coord, y_coord, distance)

    def trace_ray(self, distance=0):
        target = self.transform * Vector((0, 0, -distance))
        return self.object.rayCast(target, self.position, distance)

    @UpdateSignal.global_listener
    @simulated
    def update(self, delta_time):
        if self.visible:
            self.draw()


class Pawn(Actor):
    # Network Attributes
    alive = Attribute(True, notify=True, complain=True)
    flash_count = Attribute(0)
    health = Attribute(100, notify=True, complain=True)
    roles = Attribute(Roles(Roles.authority,
                             Roles.autonomous_proxy),
                      notify=True)
    view_pitch = Attribute(0.0)
    weapon_attachment_class = Attribute(type_of=type(Replicable),
                                        notify=True,
                                        complain=True)

    def conditions(self, is_owner, is_complaint, is_initial):
        yield from super().conditions(is_owner, is_complaint, is_initial)

        if not is_owner:
            yield "view_pitch"
            yield "flash_count"

        if is_complaint:
            yield "weapon_attachment_class"
            yield "alive"

            if is_owner:
                yield "health"

    @simulated
    def create_weapon_attachment(self, cls):
        self.weapon_attachment = cls()
        self.weapon_attachment.set_parent(self, "weapon")

        if self.weapon_attachment is not None:
            self.weapon_attachment.unpossessed()
        self.weapon_attachment.possessed_by(self)

        self.weapon_attachment.local_position = Vector()
        self.weapon_attachment.local_rotation = Euler()

    @simulated
    def get_animation_frame(self, layer=0):
        return int(self.skeleton.getActionFrame(layer))

    @simulated
    def is_playing_animation(self, layer=0):
        return self.skeleton.isPlayingAction(layer)

    @property
    def on_ground(self):
        for collider in self._registered:
            if not self.from_object(collider):
                return True
        return False

    def on_initialised(self):
        super().on_initialised()

        self.weapon_attachment = None

        # Non owner attributes
        self.last_flash_count = 0

        self.walk_speed = 4.0
        self.run_speed = 7.0
        self.turn_speed = 1.0
        self.replication_update_period = 1 / 60

        self.animations = BehaviourTree(self)
        self.animations.blackboard['pawn'] = self

    @simulated
    def on_notify(self, name):
        # play weapon effects
        if name == "weapon_attachment_class":
            self.create_weapon_attachment(self.weapon_attachment_class)

        else:
            super().on_notify(name)

    @simulated
    def play_animation(self, name, start, end, layer=0, priority=0, blend=0,
                    mode=AnimationMode.play, weight=0.0, speed=1.0,
                    blend_mode=AnimationBlend.interpolate):

        # Define conversions from Blender animations to Network animation enum
        ge_mode = {AnimationMode.play: logic.KX_ACTION_MODE_PLAY,
                AnimationMode.loop: logic.KX_ACTION_MODE_LOOP,
                AnimationMode.ping_pong: logic.KX_ACTION_MODE_PING_PONG
                }[mode]
        ge_blend_mode = {AnimationBlend.interpolate: logic.KX_ACTION_BLEND_BLEND,
                        AnimationBlend.add: logic.KX_ACTION_BLEND_ADD}[blend_mode]

        self.skeleton.playAction(name, start, end, layer, priority, blend,
                                ge_mode, weight, speed=speed,
                                blend_mode=ge_blend_mode)

    @simulated
    def stop_animation(self, layer=0):
        self.skeleton.stopAction(layer)

    @property
    def skeleton(self):
        for child in self.object.childrenRecursive:
            if isinstance(child, types.BL_ArmatureObject):
                return child

    @ActorDamagedSignal.listener
    def take_damage(self, damage, instigator, hit_position, momentum):
        self.health = int(max(self.health - damage, 0))

    @simulated
    @UpdateSignal.global_listener
    def update(self, delta_time):
        if self.weapon_attachment:
            self.update_weapon_attachment()

        # Allow remote players to determine if we are alive without seeing health
        self.update_alive_status()
        self.animations.update()

    def update_alive_status(self):
        '''Update health boolean
        Runs on authority / autonomous proxy only'''
        self.alive = self.health > 0

    @simulated
    def update_weapon_attachment(self):
        # Account for missing shots
        if self.flash_count != self.last_flash_count:
            # Protect from wrap around
            if self.last_flash_count > self.flash_count:
                self.last_flash_count = -1

            self.weapon_attachment.play_fire_effects()
            self.last_flash_count += 1

        self.weapon_attachment.local_rotation = Euler((self.view_pitch, 0, 0))


class Lamp(Actor):
    roles = Roles(Roles.authority, Roles.simulated_proxy)

    entity_class = LampObject
    entity_name = "Lamp"

    def on_initialised(self):
        super().on_initialised()

        self._intensity = None

    @property
    def intensity(self):
        return self.object.energy

    @intensity.setter
    def intensity(self, energy):
        self.object.energy = energy

    @property
    def active(self):
        return not self.intensity

    @active.setter
    def active(self, state):
        '''Modifies the lamp state by setting the intensity to a placeholder

        :param state: enabled state'''

        if not (state != (self._intensity is None)):
            return

        if state:
            self._intensity, self.intensity = None, self._intensity
        else:
            self._intensity, self.intensity = self.intensity, None


class Navmesh(Actor):
    roles = Roles(Roles.authority, Roles.none)

    entity_class = NavmeshObject
    entity_name = "Navmesh"

    def draw(self):
        self.object.draw(logic.RM_TRIS)

    def find_path(self, from_point, to_point):
        return self.object.findPath(from_point, to_point)

    def get_wall_intersection(self, from_point, to_point):
        return self.object.raycast(from_point, to_point)


class WeaponAttachment(Actor):

    roles = Attribute(Roles(Roles.authority, Roles.none))

    def on_initialised(self):
        super().on_initialised()

        self.replicate_simulated_physics = False

    def play_fire_effects(self):
        pass


class EmptyAttatchment(WeaponAttachment):

    entity_name = "Empty.002"
