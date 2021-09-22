import os
import sys
import re
import math
import random
import copy

from PIL import Image, ImageDraw

if len(sys.argv)>1:
    files = os.listdir(sys.argv[1])
else:
    files = os.listdir(".")
for f in files:
    if "__preview.png" in f:
        imgfile = os.path.join(sys.argv[1],f)
    if "__save.lua" in f:
        savefile = os.path.join(sys.argv[1],f)

if not savefile or not imgfile:
    print(f"No save and prefiew file found in {sys.argv[1]}")
    exit()
else:
    print(f"Found files:\n save: {savefile}\n preview: {imgfile}")




# Helper functions for parsing the map


def parsePosition(line):
    l = list(map(float, line.split('(')[1].split(')')[0].split(',')))
    return {'x': l[0], 'y': l[1], 'z': l[2]}


def parseSize(line):
    l = list(map(float, line.split('(')[1].split(')')[0].split(',')))
    return {'w': l[2], 'h': l[3]}


def coord2pix(x, y):
    return (x/mapsize['w']*imgx, y/mapsize['h']*imgy)


def dist(a, b):
    return math.sqrt(math.pow(a['x']-b['x'], 2)+math.pow((a['z']-b['z']), 2))

# Open up the map file and image


f = open(savefile, 'r')
text = f.readlines()
f.close()

mapimage = Image.open(
    imgfile)

imgx = mapimage.width
imgy = mapimage.height

meximage = Image.new("RGBA", [imgx, imgy], (0, 0, 0, 0))
mapdrawer = ImageDraw.Draw(meximage, "RGBA")

# Parse map elements

while not "AREA" in text.pop(0):
    pass
mapsize = parseSize(text[0])

print(f"Map size: {mapsize['w']}x{mapsize['h']}")
while not "Markers = " in text.pop(0):
    pass

armies = []
while "ARMY" in text[0]:
    armies.append(parsePosition(text[2]))
    text = text[7:]
mexes = []
while "Mex" in text[0]:
    mexes.append(parsePosition(text[8]))
    text = text[10:]

print(f"Amount of spawn points:{len(armies)}")
print(f"Amount of mexes: {len(mexes)}")


# Map parsed, strategy for distributing mexes


# Grab mexes based on distance function
def bestMex(army, freemexes, armies):
    mymexes = []
    for i in army['mex']:
        mymexes.append(mexes[i])
    distlist = list(map(lambda mex: dist((army), (mex)), freemexes))
    if mymexes:
        distown = []
        for m in freemexes:
            do = []
            for own in mymexes:
                do.append(dist(own, m))
            distown.append(min(do))

    else:
        distown = [0]*len(distlist)

    distother = []
    for m in freemexes:
        d = 10000
        for other in armies:
            if other == army:
                continue
            othermexes = []
            for i in other['mex']:
                othermexes.append(mexes[i])
            if othermexes:
                odist = []
                for othermex in othermexes:
                    odist.append(dist(m, othermex))
                min_odist = min(odist)
                d = min(min_odist, d)
        distother.append(d)

    score = list(map(lambda d, o, od: math.sqrt(
        (d*d+o*o))+50/od, distlist, distown, distother))
    d, mex = min((val, idx) for (idx, val) in enumerate(score))
    return mex, d


for i in range(len(mexes)):
    mexes[i]['i'] = i

freemexes = mexes.copy()

for army in armies:
    army['mex'] = []

for i in range(math.floor(len(mexes)/len(armies))):
    for army in armies:
        closest, score = bestMex(army, freemexes, armies)
        army['mex'].append(freemexes[closest]['i'])
        freemexes.pop(closest)

freei = list(map(lambda m: m['i'], freemexes))

# Anneel mex distribution based on cost function

def costs(army):
    am = []
    for i in army['mex']:
        am.append(mexes[i])
    costs = 0
    costs = sum(map(lambda m: pow(max(dist(army,m),0),2),am))
    return costs

def totalcosts(armies):
    cl = list(map(costs,armies))
    mc = min(cl)
    return sum(map(lambda c: math.pow(c,2),cl))


def randomSwap(armies):
    victims = random.sample(armies,2)
    l1 = victims[0]['mex']
    l2 = victims[1]['mex']
    e1 = random.choice(victims[0]['mex'][4:])
    e2 = random.choice(victims[1]['mex'][4:])
    l2[l2.index(e2)]=e1
    l1[l1.index(e1)]=e2
    pass



def anneal(armies, T):
    print(f"Old costs: {totalcosts(armies)}")
    for i in range(10000):
        narmies = copy.deepcopy(armies)
        for i in range(random.randint(1,T)):
            randomSwap(narmies)
        oc = totalcosts(armies)
        nc = totalcosts(narmies)
        if nc<oc:
            armies = narmies
        else:
            diff = nc-oc
            if random.random() < math.exp(-diff/T/1000000):
                armies = narmies
    print(f"New costs: {totalcosts(armies)}")
    return armies


for T in range(5,0,-1):
    armies = anneal(armies,T)












# Draw mexes assigned to army.

army_colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255),
               (200, 200, 0), (0, 200, 200), (200, 0, 200),
               (255, 255, 255), (64, 64, 64),
               (255, 100, 100), (100, 255, 100), (100, 100, 255),
               (155, 50, 50), (50, 155, 50), (50, 50, 155)]


for l in range(50, 1, -1):
    for i in range(len(armies)):
        army = armies[i]
        c = army_colors[i]+(127,)
        loc = [coord2pix(army['x'], army['z'])]
        if "mex" in army:
            for mexi in army["mex"]:
                mex = mexes[mexi]
                loc.append(coord2pix(mex['x'], mex['z']))

        for x, y in loc:
            mapdrawer.ellipse((x-l/2, y-l/2, x+l/2, y+l/2),
                              outline=c, fill=c, width=2)
    loc = []
    c = (0, 0, 0, 0)
    for mexi in freei:
        mex = mexes[mexi]
        loc.append(coord2pix(mex['x'], mex['z']))
    for x, y in loc:
        mapdrawer.ellipse((x-l, y-l, x+l, y+l), outline=c, fill=c, width=2)


mapimage = Image.alpha_composite(mapimage, meximage)
mapimage.save("annotated.png")
pass
