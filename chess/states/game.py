import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import ClassVar, Union, Dict

import pygame as pg

import chess.settings as s
from chess.states.state import State
from chess.panels.game.wood import Wood
from chess.panels.game.board import Board
from chess.panels.game.promotion import Promotion
from chess.panels.game.game_over import GameOver
from chess.utils.coords import Coords
from chess.player import Player, PlayerFactory
from chess.pieces import Color
from chess.panels.console import Console
from chess.utils.typewriter import TypewriterConfig


logger = logging.getLogger(Path(__file__).stem)


@dataclass
class Game(State):

    next: ClassVar[Union[None, str]] = None
    wood: Union[None, Wood] = None
    board: Union[None, Board] = None
    promotion_sprites: pg.sprite.RenderUpdates = field(
        default_factory=pg.sprite.RenderUpdates
    )
    game_over_sprites: pg.sprite.RenderUpdates = field(
        default_factory=pg.sprite.RenderUpdates
    )
    is_promoting: bool = False
    is_game_over: bool = False
    players: Dict[Color, Player] = field(default_factory=dict)
    turn: Union[None, Color] = None
    moves: int = 0
    config: dict = field(default_factory=dict)
    last_call: int = 0

    def __post_init__(self):
        self.debug_draws = [
            self.draw_grid
        ]

    def new(self, config=None):
        # initialize all variables and do all the setup for a new game
        self.wood = Wood(
            sprite_group=self.sprites,
            pos=Coords(x=1, y=1),
            size=Coords(x=18, y=18)
        )
        self.board = Board(
            sprite_group=self.sprites,
            pos=self.wood.pos
        )
        self.move = Console(
                sprite_group=self.sprites,
                title='MOVE',
                pos=Coords(x=20, y=1),
                size=Coords(x=11, y=10)
        )
        self.console = Console(
                sprite_group=self.sprites,
                pos=Coords(x=20, y=12),
                size=Coords(x=11, y=11)
        )
        self.game_over = GameOver(
            sprite_group=self.game_over_sprites,
            pos=Coords(x=13, y=7),
            size=Coords(x=5, y=6),
            color=s.LIGHTGREY
        )
        self.promotion = Promotion(
            sprite_group=self.promotion_sprites,
            pos=Coords(x=13, y=7),
            size=Coords(x=5, y=6),
            color=s.LIGHTGREY,
            margin=4,
            frame_offset=s.TILESIZE+4,
            tp_config=TypewriterConfig(
                padding=5,
                size=22,
                color=s.WHITE,
                surface_color=s.DARKGREY,
                pos='midtop'
            )
        )
        self.board.set_console(self.console)
        self.players = {k: PlayerFactory.make(name=v)(k) for k, v in config['player'].items()}
        self.turn = Color.white

    def update(self, screen, current_time, dt):
        self.current_time = current_time / 1000
        if self.debug:
            for func in self.debug_draws:
                func(screen)
        else:
            screen.fill(s.BLACK)
        self.sprites.update()
        rects = self.sprites.draw(screen)
        if self.is_promoting and self.players[self.turn].type == 'human':
            self.promotion_sprites.update()
            rects.extend(self.promotion_sprites.draw(screen))
        elif self.is_game_over:
            self.game_over_sprites.update()
            rects.extend(self.game_over_sprites.draw(screen))
        return rects

    def startup(self, current_time, persist):
        self.new(config=persist)

    def draw_grid(self, screen):
        for x in range(0, s.WIDTH, s.TILESIZE):
            pg.draw.line(screen, s.LIGHTGREY, (x, 0), (x, s.HEIGHT))
        for y in range(0, s.HEIGHT, s.TILESIZE):
            pg.draw.line(screen, s.LIGHTGREY, (0, y), (s.WIDTH, y))

    def events(self, events):
        move = None
        grid_click_pos = None
        promotion_click_pos = None
        prom = False
        for event in events:
            if event.type == pg.KEYDOWN:
                if event.key == pg.K_d:
                    self.debug = not self.debug
            if event.type == pg.MOUSEBUTTONUP:
                if self.is_promoting and self.promotion.rect.collidepoint(event.pos):
                    # check if click was in the promotion menu
                    promotion_click_pos = event.pos
                elif not self.is_promoting and self.board.rect.collidepoint(event.pos):
                    # check if click was inside chess grid
                    grid_click_pos = event.pos

        if self.check_mate() or self.draw():
            self.is_game_over = True
            return  # no more mr nice guy

        # handle turn: move or promote
        is_machine = self.players[self.turn].type == 'machine'
        if not self.is_promoting and (grid_click_pos or is_machine):
            mpos = self.board.px_to_grid(Coords(x=grid_click_pos[0], y=grid_click_pos[1])) \
                if grid_click_pos is not None else None
            move = self.players[self.turn].move(
                self.board,
                mpos
            )
        elif self.is_promoting and (promotion_click_pos or is_machine):
            prom = self.players[self.turn].promote(
                board=self.board,
                pawn=self.pawn_prom,
                promotion_selector=self.promotion,
                pos=promotion_click_pos if promotion_click_pos else None
            )
            self.is_promoting = False
            self.pawn_prom = None

        # check if there are any promotions to be done
        self.pawn_prom = self.board.promotions(self.turn)
        if self.pawn_prom:
            self.is_promoting = True
        if move:
            self.last_move = move

        # next turn happens when there are NO PENDING
        # PROMOTIONS and a MOVE or a PROMOTION took place.
        if not self.is_promoting and (move or prom):
            self.log_turn(prom)
            self.turn = Color.next(self.turn)

    def log_prom(self, prom):
        for _ in range(100):
            self.console.log(f'[DEBUG] {self.turn} has promoted a pawn to {prom}!')

    def log_turn(self, prom):
        self.moves += 1
        self.move.log(f'[{self.moves:03}]')
        msg = str(self.last_move)
        if prom:
            msg += ' promoting!'
        if self.board.is_king_checked(self.board.grid, Color.next(self.turn)):
            msg += ' check!'
        self.move.log(msg)
        self.move.log('')

    def check_mate(self):
        king = self.board.get_king(self.turn)
        return king.is_checked and not \
            self.board.get_possible_moves(self.board.grid, self.turn)

    def draw(self):
        king = self.board.get_king(self.turn)
        return not king.is_checked and not \
            self.board.get_possible_moves(self.board.grid, self.turn)
