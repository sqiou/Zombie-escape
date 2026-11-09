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


# ======================================================================
#  New levels
# ======================================================================
from game import WATER, MUD, CAR, Car, Crate, SLEEP


def level_game(level, seed=0, difficulty="Normal"):
    g = Game(difficulty, seed=seed, level=level)
    g.zombies.clear()
    g.crates.clear()
    return g


def open_row(g, y, x0, x1):
    """Turn the map into one open corridor along row y (everything else walls)."""
    m = g.map
    for yy in range(m.h):
        for xx in range(m.w):
            m.tiles[yy][xx] = BUILDING
    for xx in range(x0, x1 + 1):
        m.tiles[y][xx] = STREET
    m.reachable = {(xx, y) for xx in range(x0, x1 + 1)}
    m.cars, m.car_at = [], {}


def add_car(g, tiles):
    car = Car(tiles, 0)
    for t in tiles:
        g.map.tiles[t[1]][t[0]] = CAR
        g.map.car_at[t] = car
    g.map.cars.append(car)
    return car


class TestLevelGeneration(unittest.TestCase):
    def test_every_level_connected(self):
        for level in LEVEL_ORDER:
            for seed in range(8):
                g = Game("Hard", seed=seed, level=level)
                self.assertTrue(g.map.helipad <= g.map.reachable, (level, seed))
                self.assertTrue(g.map.safe_zone <= g.map.reachable, (level, seed))
                for z in g.zombies:
                    self.assertTrue(g.map.circle_free(z.x, z.y, z.radius))

    def test_flood_has_water_and_mud(self):
        g = Game("Normal", seed=3, level=2)
        flat = [t for row in g.map.tiles for t in row]
        self.assertGreater(flat.count(WATER), 20)
        self.assertGreater(flat.count(MUD), 5)
        self.assertEqual(g.map.tile(*g.map.start), STREET)

    def test_bridge_has_cars_and_is_long(self):
        g = Game("Normal", seed=1, level=4)
        self.assertGreater(g.map.w, GRID_W)
        self.assertGreaterEqual(len(g.map.cars), 15)
        self.assertGreaterEqual(g.player.bottles, 1)


class TestTerrain(unittest.TestCase):
    def test_astar_prefers_dry_streets(self):
        # Straight line through water (W) vs. a dry detour over the top
        grid = ["#######",
                "#.....#",
                "#.###.#",
                "#.WWW.#",
                "#######"]

        def cost(x, y):
            c = grid[y][x]
            return None if c == "#" else (WATER_PATH_COST if c == "W" else 1)
        path, _ = astar((1, 3), (5, 3), cost, 7, 5)
        self.assertNotIn((3, 3), path)

    def test_water_halves_speed_and_splashes(self):
        g = level_game(2)
        open_row(g, 5, 2, 20)
        p = g.player
        p.x, p.y = 3.5, 5.5
        g.update(0.05, move=(1, 0))
        dry = p.x - 3.5
        for x in range(2, 21):
            g.map.tiles[5][x] = WATER
        p.x = 3.5
        p.noise_timer = 0
        g.noises.clear()
        g.update(0.05, move=(1, 0))
        wet = p.x - 3.5
        self.assertAlmostEqual(wet / dry, WATER_SPEED, places=1)
        self.assertTrue(any(n.kind == "splash" and n.radius >= NOISE_SPLASH for n in g.noises))
        self.assertGreater(p.noise_level, NOISE_WALK)       # walking in water is loud

    def test_mud_slows_zombies(self):
        def distance_walked(tile):
            g = level_game(2)
            open_row(g, 5, 2, 25)
            for x in range(2, 26):
                g.map.tiles[5][x] = tile
            g.player.x, g.player.y = 24.5, 5.5
            g.diff["sight"] = 0.5
            z = Zombie(3.5, 5.5)
            z.state, z.target, z.path = INVESTIGATE, (24, 5), None
            g.zombies.append(z)
            for _ in range(20):
                g.update(0.05)
            return z.x - 3.5
        self.assertLess(distance_walked(MUD), distance_walked(STREET) * 0.75)


class TestBridge(unittest.TestCase):
    def test_cars_block_sight(self):
        g = level_game(4)
        open_row(g, 5, 2, 20)
        add_car(g, [(8, 5)])
        self.assertFalse(g.map.line_of_sight(4.5, 5.5, 12.5, 5.5))
        self.assertTrue(g.map.is_solid(8, 5))

    def test_bottle_noise_lures_zombie(self):
        g = level_game(4)
        open_row(g, 5, 2, 30)
        g.player.x, g.player.y = 3.5, 5.5
        g.diff["sight"] = 0.5                     # make sure it can't just see the player
        z = Zombie(14.5, 5.5)
        g.zombies.append(z)
        g.player.bottles = 1
        self.assertTrue(g.throw_bottle(9.5, 5.5))
        self.assertEqual(g.player.bottles, 0)
        for _ in range(16):
            g.update(0.05)
        self.assertEqual(z.state, INVESTIGATE)
        self.assertEqual(z.target, (9, 5))
        self.assertFalse(g.throw_bottle(9.5, 5.5))         # none left

    def test_bottle_hitting_car_sets_off_alarm(self):
        g = level_game(4)
        open_row(g, 5, 2, 30)
        car = add_car(g, [(10, 5), (11, 5)])
        g.player.x, g.player.y = 4.5, 5.5
        g.throw_bottle(14.5, 5.5)
        for _ in range(20):
            g.update(0.05)
        self.assertTrue(car.alarm_used)
        self.assertGreaterEqual(g.stats["alarms"], 1)

    def test_manual_alarm_needs_a_car_nearby(self):
        g = level_game(4)
        open_row(g, 5, 2, 30)
        g.player.x, g.player.y = 4.5, 5.5
        self.assertFalse(g.trigger_alarm())
        add_car(g, [(5, 5)])
        self.assertTrue(g.trigger_alarm())
        self.assertFalse(g.trigger_alarm())                # each alarm works once

    def test_reach_checkpoint_wins(self):
        g = level_game(4)
        self.assertEqual(g.heli_state, "landed")
        self.assertIsNone(g.heli_time_left)                # it never leaves
        hx, hy = sorted(g.map.helipad)[0]
        g.player.x, g.player.y = hx + 0.5, hy + 0.5
        for _ in range(int(g.board_time / 0.05) + 3):
            g.update(0.05)
        self.assertEqual(g.state, "won")


class TestSpecialZombies(unittest.TestCase):
    def test_wandering_zombie_ignores_barricades(self):
        g = empty_game()
        open_row(g, 5, 2, 12)
        g.player.x, g.player.y = 50, 50
        g.map.tiles[5][7] = BARRICADE
        g.map.barricade_hp[(7, 5)] = BARRICADE_HP
        z = Zombie(5.5, 5.5)
        z.path, z.target = [(6, 5), (7, 5), (8, 5)], (8, 5)
        g.zombies.append(z)
        for _ in range(60):
            g.update(0.05)
        self.assertEqual(g.map.tile(7, 5), BARRICADE)
        self.assertEqual(g.map.barricade_hp[(7, 5)], BARRICADE_HP)

    def test_brute_smashes_instantly_and_hits_for_two(self):
        g = level_game(5)
        open_row(g, 5, 2, 14)
        g.player.x, g.player.y = 13.5, 5.5
        g.map.tiles[5][7] = BARRICADE
        g.map.barricade_hp[(7, 5)] = g.barricade_hp
        z = Zombie(5.5, 5.5, "brute")
        z.state, z.target, z.path = INVESTIGATE, (13, 5), None
        g.zombies.append(z)
        for _ in range(40):
            g.update(0.05)
            if g.map.tile(7, 5) == STREET:
                break
        self.assertEqual(g.map.tile(7, 5), STREET)
        self.assertLess(g.time, 2.5)
        g2 = level_game(5)
        p = g2.player
        g2.zombies.append(Zombie(p.x + 0.3, p.y, "brute"))
        g2.update(0.02)
        self.assertEqual(p.hp, PLAYER_MAX_HP - 2)

    def test_screamer_alerts_whole_map_and_never_bites(self):
        g = level_game(5)
        p = g.player
        x, y = open_street_near_player(g, 2, 3)
        s = Zombie(x + 0.5, y + 0.5, "screamer")
        far = Zombie(28.5, 18.5, "normal")
        g.zombies += [s, far]
        g.update(0.02)
        self.assertEqual(s.state, CHASE)
        self.assertEqual(far.state, INVESTIGATE)
        self.assertEqual(g.stats["screams"], 1)
        s.x, s.y = p.x + 0.2, p.y
        g.update(0.02)
        self.assertEqual(p.hp, PLAYER_MAX_HP)

    def test_runner_gives_up_and_wanders(self):
        g = empty_game()
        z = Zombie(3.5, 3.5, "runner")
        z.state, z.last_seen, z.lose_timer = CHASE, (3.5, 3.5), 0.0
        g.player.x, g.player.y = 50, 50
        g.zombies.append(z)
        for _ in range(25):
            g.update(0.05)
        self.assertEqual(z.state, WANDER)

    def test_hunter_aims_ahead_of_the_player(self):
        g = level_game(5)
        open_row(g, 5, 1, 28)
        g.player.x, g.player.y = 12.5, 5.5
        z = Zombie(3.5, 5.5, "hunter")
        z.last_seen, z.last_vel, z.lose_timer = (12.5, 5.5), (2.4, 0.0), 0.0
        ix, iy = g.predict_intercept(z)
        self.assertGreater(ix, 13.5)                       # ahead, in the direction of travel
        self.assertTrue(g._walkable_goal(ix, iy))
        z.last_vel = (0.0, 0.0)
        self.assertAlmostEqual(g.predict_intercept(z)[0], 12.5)   # standing still: no lead


class TestFinalStand(unittest.TestCase):
    def test_timer_pauses_outside_zone_and_win(self):
        g = level_game(5)
        g.spawn_timer = 1e9
        self.assertEqual(g.heli_state, "incoming")
        self.assertTrue(g.in_safe_zone)
        start_left = g.heli_time_left
        out = next(t for t in sorted(g.map.reachable)
                   if t not in g.map.safe_zone and g.map.tile(*t) == STREET)
        g.player.x, g.player.y = out[0] + 0.5, out[1] + 0.5
        for _ in range(40):
            g.update(0.05)
        self.assertAlmostEqual(g.heli_time_left, start_left, places=3)
        hx, hy = sorted(g.map.helipad)[0]
        g.player.x, g.player.y = hx + 0.5, hy + 0.5
        while g.heli_state == "incoming":
            g.update(0.05)
        for _ in range(int(BOARD_TIME / 0.05) + 3):
            g.update(0.05)
        self.assertEqual(g.state, "won")

    def test_random_play_all_levels_no_crashes(self):
        import random
        for level in LEVEL_ORDER:
            for seed in range(3):
                rng = random.Random(seed)
                g = Game("Normal", seed=seed, level=level)
                mv = (0, 0)
                for i in range(30 * 60):
                    if i % 20 == 0:
                        mv = rng.choice([(1, 0), (-1, 0), (0, 1), (0, -1), (0, 0), (1, 1)])
                    throw = (g.player.x + rng.uniform(-6, 6), g.player.y + rng.uniform(-6, 6)) \
                        if rng.random() < 0.01 else None
                    g.update(1 / 30, mv, run=rng.random() < 0.3, place=rng.random() < 0.02,
                             throw=throw, alarm=rng.random() < 0.01, flashlight=rng.random() < 0.01)
                    g.pop_events()
                    for z in g.zombies:
                        self.assertTrue(g.map.circle_free(z.x, z.y, z.radius) or z.attacking)
                    if g.state != "playing":
                        break


class TestHospital(unittest.TestCase):
    def test_bsp_rooms_beds_and_far_elevator(self):
        for seed in range(6):
            g = Game("Normal", seed=seed, level=3)
            m = g.map
            self.assertGreaterEqual(len(m.rooms), 5)
            self.assertTrue(m.beds)
            sx, sy = m.start
            ex, ey = sorted(m.helipad)[0]
            self.assertGreater(abs(ex - sx) + abs(ey - sy), 10)       # the lift is far away
            self.assertTrue(any(z.state == SLEEP for z in g.zombies))

    def test_darkness_and_flashlight_vision(self):
        g = level_game(3)
        dark = len(g.visible)
        self.assertTrue(g.toggle_flashlight())
        best = 0
        for facing in ((1.0, 0.0), (-1.0, 0.0), (0.0, 1.0), (0.0, -1.0)):
            g.player.facing = facing
            g.update_fog()
            best = max(best, len(g.visible))
        self.assertGreater(best, dark)
        lit = Game("Normal", seed=0, level=1)
        self.assertLess(g.view_radius, lit.view_radius)

    def test_flashlight_makes_you_easier_to_see(self):
        g = level_game(3)
        z = Zombie(1.5, 1.5)
        off = g.sight_range(z)
        g.player.flashlight = True
        self.assertGreater(g.sight_range(z), off * 2)

    def test_battery_runs_out(self):
        g = level_game(3)
        g.toggle_flashlight()
        for _ in range(int(BATTERY_MAX / BATTERY_DRAIN / 0.05) + 5):
            g.update(0.05)
        self.assertFalse(g.player.flashlight)
        self.assertFalse(g.toggle_flashlight())             # can't turn it back on
        g.crates.append(Crate(*g.player.tile, "battery"))
        g.update(0.02)
        self.assertTrue(g.toggle_flashlight())

    def test_sleeper_ignores_walking_but_wakes_to_running(self):
        g = level_game(3)
        open_row(g, 5, 2, 20)
        z = Zombie(10.5, 5.5)
        z.state = SLEEP
        g.zombies.append(z)
        g.emit_noise(8.5, 5.5, NOISE_WALK, "step")         # 2 tiles away, quiet
        self.assertEqual(z.state, SLEEP)
        g.emit_noise(6.5, 5.5, NOISE_RUN, "step")          # 4 tiles away, loud
        self.assertEqual(z.state, INVESTIGATE)

    def test_sleeper_wakes_when_you_bump_into_it(self):
        g = level_game(3)
        open_row(g, 5, 2, 20)
        g.player.x, g.player.y = 9.6, 5.5
        z = Zombie(10.5, 5.5)
        z.state = SLEEP
        g.zombies.append(z)
        g.update(0.02)
        self.assertNotEqual(z.state, SLEEP)

    def test_elevator_win_flow(self):
        g = level_game(3)
        p = g.player
        for _ in range(3):
            g.crates.append(Crate(*p.tile, "radio"))
            g.update(0.02)
        self.assertEqual(g.heli_state, "incoming")
        while g.heli_state == "incoming":
            g.update(0.05)
        hx, hy = sorted(g.map.helipad)[0]
        p.x, p.y = hx + 0.5, hy + 0.5
        for _ in range(int(BOARD_TIME / 0.05) + 3):
            g.update(0.05)
        self.assertEqual(g.state, "won")
        self.assertIn("elevator", g.reason)


if __name__ == "__main__":
    unittest.main(verbosity=2)
