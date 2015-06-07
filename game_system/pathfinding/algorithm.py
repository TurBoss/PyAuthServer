from collections import deque, namedtuple
from heapq import heappop, heappush

from ..geometry.utilities import triangle_area_squared
from ..coordinates import Vector
from ..iterators import BidirectionalIterator

from network.iterators import look_ahead

__all__ = "Funnel", "PathNotFoundException", "AlgorithmNotImplementedException", "AStarAlgorithm", "FunnelAlgorithm", \
          "PathfinderAlgorithm"


forward_vector = Vector((0, 1, 0))
EndPortal = namedtuple("EndPortal", ["left", "right"])
BoundVector = type("BoundVector", (Vector,), {"__slots__": "data"})


def manhattan_distance_heuristic(a, b):
    return (b.position - a.position).length_squared


class Funnel:
    __slots__ = "left", "right", "_apex", "_apex_callback"

    def __init__(self, apex, left, right, on_apex_changed):
        self.left = left
        self.right = right
        self._apex = apex
        self._apex_callback = on_apex_changed

    @property
    def apex(self):
        return self._apex

    @apex.setter
    def apex(self, value):
        self._apex = value
        self._apex_callback(value)

    def update(self, portals):
        portals = BidirectionalIterator(portals)
        left_index = right_index = portals.index

        # Increment index and then return entry at index
        for portal in portals:
            # Check if left is inside of left margin
            if triangle_area_squared(self.apex, self.left, portal.left) >= 0.0:
                # Check if left is inside of right margin or
                # we haven't got a proper funnel
                if self.apex == self.left or (triangle_area_squared(self.apex, self.right, portal.left) < 0.0):
                    # Narrow funnel
                    self.left = portal.left
                    left_index = portals.index

                else:
                    # Otherwise add apex to path
                    self.left = self.apex = self.right
                    # Set portal to consider from the corner we pivoted around
                    # This index is incremented by the for loop
                    portals.index = right_index
                    continue

            # Check if right is inside of right margin
            if triangle_area_squared(self.apex, self.right, portal.right) <= 0.0:
                # Check if right is inside of left margin or
                # we haven't got a proper funnel
                if self.apex == self.right or (triangle_area_squared(self.apex, self.left, portal.right) > 0.0):
                    # Narrow funnel
                    self.right = portal.right
                    right_index = portals.index

                else:
                    # Otherwise add apex to path
                    self.right = self.apex = self.left
                    # Set portal to consider from the corner we pivoted around
                    # This index is incremented by the for loop
                    portals.index = left_index
                    continue


class PathNotFoundException(Exception):
    pass


class AlgorithmNotImplementedException(Exception):
    pass


class AStarNode:

    g_score = 0
    f_score = 0
    h_score = 0

    def get_g_score_from(self, other):
        raise NotImplementedError


class AStarGoalNode(AStarNode):

    def get_h_score_from(self, other):
        raise NotImplementedError


class AStarAlgorithm:

    def __init__(self):
        pass

    def is_finished(self, goal, current, path):
        raise NotImplementedError

    @staticmethod
    def reconstruct_path(node, goal, path):
        result = deque()
        while node:
            result.appendleft(node)
            node = path.get(node)

        return result

    def find_path(self, goal, start=None):
        if start is None:
            start = goal

        open_set = {start}
        closed_set = set()
        path = {}
        f_scored = [(0, start)]

        is_complete = self.is_finished

        while open_set:
            current = heappop(f_scored)[1]

            open_set.remove(current)
            closed_set.add(current)

            if is_complete(current, goal, path):
                return self.reconstruct_path(current, goal, path)

            for neighbour in current.neighbours:
                if neighbour in closed_set:
                    continue

                tentative_g_score = current.g_score + neighbour.get_g_score_from(current)

                if neighbour not in open_set or tentative_g_score < neighbour.g_score:
                    path[neighbour] = current
                    neighbour.g_score = tentative_g_score
                    heappush(f_scored, (tentative_g_score + goal.get_h_score_from(neighbour), neighbour))

                    if neighbour not in open_set:
                        open_set.add(neighbour)

        raise PathNotFoundException("Couldn't find path for given nodes")


class FunnelAlgorithm:

    def find_path(self, source, destination, nodes):
        path = [source]

        # Account for main path
        portals = [source.get_portal_to(destination) for source, destination in look_ahead(nodes)]
        portals.append(EndPortal(destination, destination))

        funnel = Funnel(source, source, source, path.append)
        funnel.update(portals)

        # Account for last destination point
        if funnel is None:
            return []

        path.append(destination)
        return path


class PathfinderAlgorithm:

    def __init__(self, low_fidelity, high_fidelity, spatial_lookup):
        self.low_resolution = low_fidelity
        self.high_resolution = high_fidelity
        self.spatial_lookup = spatial_lookup

    def find_path(self, source, destination, nodes, low_resolution=False):
        source_node = self.spatial_lookup(source)
        destination_node = self.spatial_lookup(destination)

        try:
            path_finder = self.low_resolution.find_path

        except AttributeError:
            raise AlgorithmNotImplementedException("Couldn't find low resolution finder algorithm")

        low_resolution_path = path_finder(source_node, destination_node, nodes)
        if low_resolution:
            return low_resolution_path

        try:
            path_finder = self.high_resolution.find_path

        except AttributeError:
            raise AlgorithmNotImplementedException("Couldn't find high resolution finder algorithm")

        high_resolution_path = path_finder(source, destination, low_resolution_path)
        return high_resolution_path