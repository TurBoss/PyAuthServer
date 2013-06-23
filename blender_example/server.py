from bge import logic
from bge_network import Game, Actor, QuitGame

from rules import TeamDeathMatch
from network import WorldInfo, Netmodes

from random import randint

from actors import Player

# Set network mode
WorldInfo.netmode = Netmodes.server
WorldInfo.rules = TeamDeathMatch

# Add random actors
def random_spawn(n):
    '''Spawns randomly positioned actors'''
    for i in range(n):
        a = Player()
        a.physics.position[:] = randint(-10, 10), randint(-10, 10), 20

game = Game(addr="127.0.0.1", port=1200)

#random_spawn(5)

def main(cont):  
    try:
        game.update()    
    except QuitGame:
        logic.endGame()  
        print("Ended game")
    