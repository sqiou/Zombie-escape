"""
test_game.py - automated tests for the game logic and AI.

Run:   python -m unittest test_game.py -v
(No pygame needed: the logic in game.py is independent of graphics.)
"""

import unittest

from settings import *
from pathfinding import astar, bfs_reachable
from game import (Game, CityMap, Zombie, Noise, STREET, BUILDING, BARRICADE,
                  WANDER, INVESTIGATE, CHASE, dist)


def grid_cost(grid):
    """Make a cost function from a list of strings: '#' wall, 'B' barricade."""
    def cost(x, y):
        c = grid[y][x]
        return None if c == "#" else (BARRICADE_PATH_COST if c == "B" else 1)
    return cost


def empty_game(seed=0, difficulty="Normal"):
    """A game with all zombies and crates removed, for controlled tests."""
    g = Game(difficulty, seed=seed)
    g.zombies.clear()
    g.crates.clear()
    return g


def open_street_near_player(g, min_d=2, max_d=4):
    p = g.player
    for (x, y) in sorted(g.map.reachable):
        d = dist(x + 0.5, y + 0.5, p.x, p.y)
        if min_d <= d <= max_d and g.map.tile(x, y) == STREET and \
                g.map.line_of_sight(x + 0.5, y + 0.5, p.x, p.y):
            return x, y
    raise AssertionError("no suitable tile")


class TestAStar(unittest.TestCase):
    def test_straight_line(self):
        grid = [".....", ".....", "....."]
        path, _ = astar((0, 1), (4, 1), grid_cost(grid), 5, 3)
        self.assertEqual(path, [(1, 1), (2, 1), (3, 1), (4, 1)])

    def test_goes_around_wall(self):
        grid = [".....",
                ".###.",
                "....."]
        path, _ = astar((0, 1), (4, 1), grid_cost(grid), 5, 3)
        self.assertEqual(len(path), 6)                   # optimal detour
        self.assertTrue(all(grid[y][x] != "#" for x, y in path))

    def test_unreachable(self):
        grid = ["..#..", "..#..", "..#.."]
        path, _ = astar((0, 0), (4, 0), grid_cost(grid), 5, 3)
        self.assertIsNone(path)

    def test_prefers_detour_over_cheap_barricade(self):
        # Through the barricade costs 6+1; the detour costs 6 steps -> detour wins.
        grid = [".....",
                "##B##",
                "....."]
        grid_open = [".....",
                     "##B#.",
                     "....."]
        path, _ = astar((2, 0), (2, 2), grid_cost(grid_open), 5, 3)
        self.assertNotIn((2, 1), path)
        # With no detour at all, A* must go through the barricade.
        path, _ = astar((2, 0), (2, 2), grid_cost(grid), 5, 3)
        self.assertIn((2, 1), path)

    def test_same_tile(self):
        self.assertEqual(astar((1, 1), (1, 1), grid_cost(["..", ".."]), 2, 2)[0], [])

    def test_bfs(self):
        grid = ["..#..", "..#..", "..#.."]
        self.assertEqual(len(bfs_reachable((0, 0), grid_cost(grid), 5, 3)), 6)


class TestMap(unittest.TestCase):
    def test_many_maps_connected(self):
        for seed in range(40):
            g = Game("Normal", seed=seed)
            m = g.map
            self.assertTrue(m.helipad <= m.reachable, seed)
            self.assertIn(m.start, m.reachable)
            # border is solid
            self.assertTrue(all(m.tiles[0][x] == BUILDING for x in range(m.w)))
            # all crates and zombies are reachable
            for c in g.crates:
                self.assertIn((c.x, c.y), m.reachable)
            for z in g.zombies:
                self.assertIn(z.tile, m.reachable)
            self.assertEqual(sum(c.kind == "radio" for c in g.crates), RADIO_PARTS)

    def test_zombies_spawn_far_from_player(self):
        for seed in range(20):
            g = Game("Hard", seed=seed)
            for z in g.zombies:
                self.assertGreaterEqual(dist(z.x, z.y, g.player.x, g.player.y), ZOMBIE_MIN_SPAWN_DIST - 0.01)

    def test_line_of_sight(self):
        g = empty_game()
        m = g.map
        for y in range(m.h):
            for x in range(m.w):
                m.tiles[y][x] = STREET
        m.tiles[5][5] = BUILDING
        self.assertFalse(m.line_of_sight(3.5, 5.5, 7.5, 5.5))
        self.assertTrue(m.line_of_sight(3.5, 3.5, 7.5, 3.5))
        m.tiles[5][5] = BARRICADE                   # barricades don't block sight
        self.assertTrue(m.line_of_sight(3.5, 5.5, 7.5, 5.5))


class TestPlayer(unittest.TestCase):
    def test_cannot_walk_through_buildings(self):
        for seed in range(10):
            g = empty_game(seed)
            for i in range(600):
                g.update(1 / 30, move=[(1, 0), (0, 1), (-1, 0), (0, -1)][(i // 40) % 4], run=True)
                self.assertTrue(g.map.circle_free(g.player.x, g.player.y, g.player.radius))

    def test_running_is_louder_and_uses_stamina(self):
        g = empty_game()
        g.update(0.05, move=(0, 1), run=True)
        self.assertTrue(g.player.running)
        self.assertEqual(g.player.noise_level, NOISE_RUN)
        self.assertLess(g.player.stamina, STAMINA_MAX)
        g.update(0.05, move=(0, 1), run=False)
        self.assertEqual(g.player.noise_level, NOISE_WALK)
        g.update(0.05, move=(0, 0))
        self.assertEqual(g.player.noise_level, 0)

    def test_exhaustion(self):
        g = empty_game()
        for _ in range(int(STAMINA_MAX / STAMINA_DRAIN / 0.05) + 5):
            g.update(0.05, move=(1, 0) if int(g.time) % 2 else (-1, 0), run=True)
        self.assertTrue(g.player.exhausted)
        self.assertFalse(g.player.running)

    def test_place_barricade(self):
        g = empty_game()
        p = g.player
        p.place_dir = (1, 0)
        tx, ty = p.tile[0] + 1, p.tile[1]
        self.assertEqual(g.map.tile(tx, ty), STREET)
        before = p.barricades
        self.assertTrue(g.try_place_barricade())
        self.assertEqual(g.map.tile(tx, ty), BARRICADE)
        self.assertEqual(p.barricades, before - 1)
        self.assertFalse(g.try_place_barricade())          # tile now occupied
        p.barricades = 0
        p.place_dir = (0, 1)
        self.assertFalse(g.try_place_barricade())          # none left

    def test_cannot_barricade_on_zombie(self):
        g = empty_game()
        p = g.player
        p.place_dir = (1, 0)
        g.zombies.append(Zombie(p.tile[0] + 1.5, p.tile[1] + 0.5))
        self.assertFalse(g.try_place_barricade())

    def test_pickups(self):
        from game import Crate
        g = empty_game()
        p = g.player
        p.hp = 1
        g.crates.append(Crate(*p.tile, "medkit"))
        g.update(0.02)
        self.assertEqual(p.hp, 2)
        b = p.barricades
        g.crates.append(Crate(*p.tile, "barricade"))
        g.update(0.02)
        self.assertEqual(p.barricades, b + 2)


class TestZombieAI(unittest.TestCase):
    def test_zombie_sees_player_and_chases(self):
        g = empty_game()
        x, y = open_street_near_player(g)
        z = Zombie(x + 0.5, y + 0.5)
        g.zombies.append(z)
        g.update(0.02)
        self.assertEqual(z.state, CHASE)
        self.assertTrue(z.path is not None)

    def test_chasing_zombie_gets_closer(self):
        g = empty_game()
        x, y = open_street_near_player(g, 3, 4.5)
        z = Zombie(x + 0.5, y + 0.5)
        g.zombies.append(z)
        d0 = dist(z.x, z.y, g.player.x, g.player.y)
        for _ in range(20):
            g.update(0.03)
        self.assertLess(dist(z.x, z.y, g.player.x, g.player.y), d0)

    def test_hears_noise_and_investigates(self):
        g = empty_game()
        z = Zombie(10.5, 10.5)
        g.zombies.append(z)
        g.emit_noise(12.5, 10.5, 5, "test")
        self.assertEqual(z.state, INVESTIGATE)
        self.assertEqual(z.target, (12, 10))
        g.emit_noise(25.5, 18.5, 2, "far")      # out of hearing range
        self.assertEqual(z.target, (12, 10))

    def test_chasing_zombie_ignores_noise(self):
        z = Zombie(1.5, 1.5)
        z.state = CHASE
        z.hear(Noise(5, 5, 10, "test"))
        self.assertEqual(z.state, CHASE)

    def test_groan_alerts_other_zombies(self):
        g = empty_game()
        x, y = open_street_near_player(g, 2, 3)
        spotter = Zombie(x + 0.5, y + 0.5)
        p = g.player
        # A friend within groan range of the spotter, but too far to see the player itself.
        friend_tile = next(
            (tx, ty) for (tx, ty) in sorted(g.map.reachable)
            if dist(tx + 0.5, ty + 0.5, p.x, p.y) > g.diff["sight"] + 0.3
            and dist(tx + 0.5, ty + 0.5, spotter.x, spotter.y) < NOISE_GROAN - 0.3)
        friend = Zombie(friend_tile[0] + 0.5, friend_tile[1] + 0.5)
        g.zombies += [spotter, friend]
        g.update(0.02)
        self.assertEqual(spotter.state, CHASE)
        self.assertEqual(len([n for n in g.noises if n.kind == "groan"]), 1)
        self.assertEqual(friend.state, INVESTIGATE)            # came to help
        self.assertEqual(friend.target, (int(p.x), int(p.y)))  # heading for the player

    def test_lose_sight_then_investigate_then_wander(self):
        g = empty_game()
        z = Zombie(25.5, 17.5)
        g.zombies.append(z)
        g.player.x, g.player.y = 1.5, 1.5
        z.state = CHASE
        z.last_seen = (20.5, 17.5)
        for _ in range(int((LOSE_SIGHT_TIME + 0.2) / 0.05)):
            g.update(0.05)
        self.assertIn(z.state, (INVESTIGATE, WANDER))
        for _ in range(400):
            g.update(0.05)
            if z.state == WANDER:
                break
        self.assertEqual(z.state, WANDER)

    def test_zombie_breaks_barricade_when_no_other_way(self):
        g = empty_game()
        m = g.map
        # Build a corridor: walls everywhere except row 5, x = 2..10
        for y in range(m.h):
            for x in range(m.w):
                m.tiles[y][x] = BUILDING
        for x in range(2, 11):
            m.tiles[5][x] = STREET
        m.reachable = {(x, 5) for x in range(2, 11)}
        g.player.x, g.player.y = 10.5, 5.5
        m.tiles[5][7] = BARRICADE
        m.barricade_hp[(7, 5)] = BARRICADE_HP
        z = Zombie(3.5, 5.5)
        z.state = INVESTIGATE
        z.target = (10, 5)
        z.path = None
        g.zombies.append(z)
        for _ in range(int((BARRICADE_HP + 4) / 0.05)):
            g.update(0.05)
        self.assertEqual(m.tile(7, 5), STREET)              # smashed
        self.assertGreater(z.x, 7.0)                        # and walked through
        self.assertGreaterEqual(g.stats["barricades_broken"], 1)

    def test_zombies_never_inside_walls(self):
        for seed in range(6):
            g = Game("Hard", seed=seed)
            for i in range(900):
                g.update(1 / 30, move=[(1, 0), (0, 1), (1, 1), (0, 0)][(i // 60) % 4], run=i % 120 < 30,
                         place=i % 97 == 0)
                for z in g.zombies:
                    self.assertTrue(g.map.circle_free(z.x, z.y, z.radius) or z.attacking,
                                    f"seed {seed} zombie {z.id} inside wall at {z.x:.2f},{z.y:.2f}")
                if g.state != "playing":
                    break

    def test_bite_reduces_health_with_invulnerability(self):
        g = empty_game()
        p = g.player
        z = Zombie(p.x + 0.3, p.y)
        g.zombies.append(z)
        g.update(0.02)
        self.assertEqual(p.hp, PLAYER_MAX_HP - 1)
        g.update(0.02)
        self.assertEqual(p.hp, PLAYER_MAX_HP - 1)     # invulnerable right after a bite
        self.assertGreater(z.stun, 0)


class TestHelicopter(unittest.TestCase):
    def test_full_win_flow(self):
        g = empty_game()
        from game import Crate
        p = g.player
        for _ in range(RADIO_PARTS):
            g.crates.append(Crate(*p.tile, "radio"))
            g.update(0.02)
        self.assertEqual(g.parts_collected, RADIO_PARTS)
        self.assertEqual(g.heli_state, "incoming")
        while g.heli_state == "incoming":
            g.update(0.05)
        self.assertEqual(g.heli_state, "landed")
        hx, hy = sorted(g.map.helipad)[0]
        p.x, p.y = hx + 0.5, hy + 0.5
        for _ in range(int(BOARD_TIME / 0.05) + 3):
            g.update(0.05)
        self.assertEqual(g.state, "won")

    def test_helicopter_leaves(self):
        g = empty_game()
        g.heli_state = "incoming"
        g.heli_arrive_at = 0.0
        for _ in range(int((HELI_WAIT_TIME + 1) / 0.05)):
            g.update(0.05)
        self.assertEqual(g.state, "lost")
        self.assertIn("left", g.reason)


class TestLongSimulation(unittest.TestCase):
    def test_random_play_no_crashes(self):
        import random
        for d in DIFFICULTY:
            for seed in range(5):
                rng = random.Random(seed)
                g = Game(d, seed=seed)
                mv = (0, 0)
                for i in range(30 * 120):
                    if i % 20 == 0:
                        mv = rng.choice([(1, 0), (-1, 0), (0, 1), (0, -1), (0, 0), (1, 1), (-1, 1)])
                    g.update(1 / 30, mv, run=rng.random() < 0.3, place=rng.random() < 0.02)
                    g.pop_events()
                    if g.state != "playing":
                        break
                self.assertIn(g.state, ("playing", "won", "lost"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
