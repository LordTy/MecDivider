#!/usr/bin/env python3

import os
import sys
import re
import math
import random
import copy
import time

from argparse import ArgumentParser
from PIL import Image, ImageDraw
import numpy as np

import matplotlib
import pandas as pd 

from flask import Flask,request,render_template, redirect
from werkzeug.datastructures import _unicodify_header_value
import logging

# Helper functions for parsing the map
mapsize={'w':0,'h':0}
mexes = []
imgx,imgy = (0,0)
startingmexes = 0


army_colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255),
            (200, 200, 0), (0, 200, 200), (200, 0, 200),
            (255, 255, 255), (64, 64, 64),
            (255, 100, 100), (100, 255, 100), (100, 100, 255),
            (155, 50, 50), (50, 155, 50), (50, 50, 155)]

def parsePosition(line):
    l = list(map(float, line.split('(')[1].split(')')[0].split(',')))
    return {'x': l[0], 'y': l[1], 'z': l[2]}


def parseSize(line):
    l = list(map(float, line.split('(')[1].split(')')[0].split(',')))
    return {'w': l[2], 'h': l[3]}


def coord2pix(e):
    return (e.x/mapsize['w']*imgx, e.z/mapsize['h']*imgy)


def dist(a, b):
    return math.sqrt(math.pow(a.x-b.x, 2)+math.pow((a.z-b.z), 2))

# Grab mexes based on distance function
def distancelist(target: pd.DataFrame, list: pd.DataFrame):
    return ((list.x-target.x) ** 2 + (list.z-target.z) ** 2).pow(0.5)


def distancelist_min(target, list):
    result = distancelist(list, target).min()
    return result


def army_distancelist_cached(targets, army):
    return mex2army.loc[list(targets), list(army)]


def mex_distancelist_cached(targets, others):
    return mex2mex.loc[list(targets), list(others)]


def distancelist_min_cached(targets, others):
    result = mex_distancelist_cached(targets, others)
    return result.min(axis=1)


def bestMex(mexes, armies, army):
    freemexes = mexes[mexes['owner']==-1]
    mymexes = mexes[mexes['owner']==army]

    distances = army_distancelist_cached(freemexes.index, [army])[army]

    if mymexes.empty:
        mydistances = 0
    else:
        mydistances = distancelist_min_cached(freemexes.index, mymexes.index)

    othermexes = mexes[(mexes['owner']!=-1) & (mexes['owner']!=army)]

    if othermexes.empty:
        otherdistances = 10000
    else:
        otherdistances = distancelist_min_cached(freemexes.index, othermexes.index)

    
    score = np.sqrt(np.square(distances)+np.square(mydistances))+50/otherdistances


    mex = score.idxmin()
    d = score.loc[mex]
    return int(mex), float(d)

armycosts = [];

def costs(army,mexes):
    return np.sum(np.square(army_distancelist_cached(mexes[mexes['owner']==army.name].index,[army.name]))).iloc[0]


def totalcosts(armies,mexes):
    global armycosts
    if len(armycosts)==0:
        for i,army in armies.iterrows():
            armycosts.insert(i,{'dirty':False,'costs':costs(army,mexes)})

    cl = [];
    for ac in range(len(armycosts)):
        army = armycosts[ac]
        if army['dirty']==False:
            cl.append(army['costs'])
        else:
            army['costs']=costs(armies.loc[ac],mexes)
            cl.append(army['costs'])
            army['dirty']==True
    return np.sum(np.square(cl))


def randomSwap(armies,mexes):
    global armycosts
    validpair = False
    while not validpair:
        e1 = random.randint(0,len(mexes)-1)
        e2 = random.randint(0,len(mexes)-1)
        victims= mexes[e1],mexes[e2]
        validpair = not mexStarter_np_cache[e1] and not mexStarter_np_cache[e2] and not victims[0]==victims[1]


    
    # e1 = mexes[(mexes['owner']==victims[0]) & (mexes['starting']==False)].sample(n=1).index
    # e2 = mexes[(mexes['owner']==victims[1]) & (mexes['starting']==False)].sample(n=1).index
    mexes[e1]=victims[1]
    mexes[e2]=victims[0]

    armycosts[victims[0]]['costs']+= math.pow(mex2army_np_cache[e2,victims[0]],2) - math.pow(mex2army_np_cache[e1,victims[0]],2)
    armycosts[victims[1]]['costs']+= math.pow(mex2army_np_cache[e1,victims[1]],2) - math.pow(mex2army_np_cache[e2,victims[1]],2)

    armycosts[victims[0]]['dirty']=False
    armycosts[victims[1]]['dirty']=False

    return mexes

def anneal(armies, mexes, T,cycles):
    print(f"Old costs: {totalcosts(armies,mexes)}")
    global armycosts,mexOwner_np_cache
    
    for i in range(cycles):
        newmexes = mexOwner_np_cache.copy()
        oc = totalcosts(armies,mexes)
        oldcosts = copy.deepcopy(armycosts)
        for i in range(random.randint(1, T)):
            newmexes = randomSwap(armies,newmexes)
        nc = totalcosts(armies,newmexes)

        if nc < oc:
            mexOwner_np_cache=newmexes
        else:
            diff = nc-oc
            if random.random() < math.exp(-diff/T/1000000):
                mexOwner_np_cache=newmexes
            else:
                armycosts=oldcosts
    print(f"New costs: {totalcosts(armies,mexes)}")
    return armies, mexes


def parseMap(mapfile, imgfile):
    f = open(mapfile, 'r')
    text = f.readlines()
    f.close()

    mapimage = Image.open(
        imgfile)

    global imgx, imgy
    imgx = mapimage.width
    imgy = mapimage.height

    while not "AREA" in text.pop(0):
        pass
    global mapsize
    mapsize = parseSize(text[0])

    print(f"Map size: {mapsize['w']}x{mapsize['h']}")
    while not "Markers = " in text.pop(0):
        pass

    armies = []
    mexes = []
    while "ARMY" in text[0]:
        armies.append(parsePosition(text[2]))
        text = text[7:]
    while "Mex" in text[0]:
        mexes.append(parsePosition(text[8]))
        text = text[10:]

    armies_df = pd.DataFrame(armies)

    mexes_df =pd.DataFrame(mexes)
    mexes_df['owner']=-1
    mexes_df['starting']=False
    return ((imgx,imgy),mapimage,armies_df,mexes_df)

def drawTerritory(mapdrawer, armies, mexes):
    global army_colors



    mexes['pos'] = mexes.apply(coord2pix,axis=1)
    armies['pos'] = armies.apply(coord2pix,axis=1)

    drawtargets = []

    for i,army in armies.iterrows():
        c = army_colors[i]+(127,)
        targets = [(army.pos[0],army.pos[1])]
        for m,mex in mexes[mexes['owner']==i].iterrows():
            targets.append((mex.pos[0],mex.pos[1]))
        drawtargets.append({'color':c,'targets':targets})

    c = (0, 0, 0, 0)
    targets = []
    for m, mex in mexes[mexes['owner']==-1].iterrows():
            targets.append((mex.pos[0],mex.pos[1]))
    drawtargets.append({'color':c,'targets':targets})

    for l in range(50, 1, -1):
        for t in drawtargets:
            c=t['color']
            for p in t['targets']:
                mapdrawer.ellipse((p[0]-l/2,p[1]-l/2, p[0]+l/2, p[1]+l/2),
                                  fill=c)

def claimMexes(armies, mexes):
    for i in range(math.floor(len(mexes)/len(armies))):
        for army,pos in armies.iterrows():
            closest, score = bestMex(mexes,armies,army)
            mexes.loc[closest,('owner')]=army
            if dist(mexes.loc[closest],armies.loc[army])<16:
                mexes.loc[closest,('starting')]=True


    return len(mexes[(mexes['owner']==0) & (mexes['starting']==True)])

def createMexImage(mapimage,mexes,armies,output):
    meximage = Image.new("RGBA", [imgx, imgy], (0, 0, 0, 0))
    mapdrawer = ImageDraw.Draw(meximage, "RGBA")

    t = time.time()
    drawTerritory(mapdrawer, armies, mexes)
    te = time.time()-t
    print(f"Draw Ellapsed time: {te}")

    mapimage = mapimage.convert("RGBA")
    mapimage = Image.alpha_composite(mapimage, meximage)
    mapimage.save(output)


def main():
    parser = ArgumentParser(description='Calculate the distribution of mass extractors.')
    parser.add_argument('-p', '--preview', dest='img',  type=str, required=True,
                        help='Preview (PNG) file.')
    parser.add_argument('-s', '--save',    dest='save', type=str, required=True,
                        help='Save (LUA) file.')
    parser.add_argument('-o', '--out',     dest='out',  type=str, default='annotated.png',
                        help='Output file.')
    parser.add_argument('-t','--temperature', dest='temp', type=int, default=5,
                    help="The amount of annealing cycles")
    parser.add_argument('-c','--cycles', dest='cycles', type=int, default=10000,
                    help="The amount of annealing cycles")             
    parser.add_argument('-w','--web', dest='web', type=bool, default=True,
                    help="THost webserver for editting")   
    parser.add_argument('-u','--baseurl', dest='baseurl', type=str, default="http://localhost:8080/",
                    help="The base url for the webserver")     
    args = parser.parse_args()

    # Parse map elements
    global mexes
    mapdata,mapimage,armies,mexes = parseMap(args.save, args.img)
    global imgx, imgy, mex2mex, mex2army
    global mex2army_np_cache
    imgx = mapdata[0]
    imgy = mapdata[1]

    mex2mex = mexes.apply(distancelist, result_type='expand', axis=1, list=mexes)
    mex2army = mexes.apply(distancelist, result_type='expand', axis=1, list=armies)
    mex2army_np_cache = np.array(mex2army)

    print(f"Amount of spawn points:{len(armies)}")
    print(f"Amount of mexes: {len(mexes)}")

    ## Map parsed, strategy for distributing mexes

    # Claim mexes based on distance
    t = time.time()
    startingmexes = claimMexes(armies, mexes)
    te = time.time()-t
    print(f"Amount of starting mexes: {startingmexes}")
    print(f"Claim Ellapsed time: {te}")



    # Optimize mex distribution by swapping
    t = time.time()

    global mexOwner_np_cache, mexStarter_np_cache
    mexOwner_np_cache = np.array(mexes['owner'])
    mexStarter_np_cache = np.array(mexes['starting'])
    for T in range(args.temp, 0, -1):
       armies,mexes = anneal(armies,mexes, T, args.cycles)

    mexes['owner']=mexOwner_np_cache
    
    te = time.time()-t


    print(f"Anneal Ellapsed time: {te}")
    # Draw mexes on map
    createMexImage(mapimage,mexes,armies,args.out)


    if args.web:

        createMexImage(mapimage,mexes,armies,os.path.join("static",args.out))
        app = Flask(__name__)

        log = logging.getLogger('werkzeug')
        log.setLevel(logging.ERROR)

        @app.route('/meximg/<player>', methods=['POST','GET'])
        @app.route('/meximg', methods=['POST','GET'])
        def update_mex_image(player=None):
            global mexes
            pos = None
            for k in request.args.to_dict().keys():
                pos = k
            if not pos is None:
                x,y =map(int,pos.split(','))
                print(f"X:{x} ,Y:{y}")
                x *= imgx/512
                y *= imgy/512

                mindist = 256
                clmex = -1
                for m,mex in mexes.iterrows():
                    d = math.sqrt(pow(mex.pos[0]-x,2)+pow(mex.pos[1]-y,2))
                    if d<mindist: mindist = d;clmex=m
                print(f"Selected mex {clmex} at {x},{y}")
                if player:
                    mexes.loc[clmex,('owner')]=int(player)
            rnum = time.time_ns()
            pcolor = None
            if player:
                url = f"/meximg/{player}"
                pcolor = c = '%02x%02x%02x' % army_colors[int(player)]
            else:
                player = -1
                url = "/meximg"

            armylist = []
            for i,army in armies.iterrows():
                pass
                c = '%02x%02x%02x' % army_colors[i]
                armylist.append({'id':i,'color':c, 'url':f"/meximg/{i}"})

            createMexImage(mapimage,mexes,armies,os.path.join("static",args.out))
            
            return render_template('mexshow.html',player=int(player),url=url,rnum=rnum,armies=armylist,pcolor=pcolor)

        @app.route('/changecolor/<player>', methods=['POST'])
        def update_color(player):
            c= request.form['armycolor']
            value = c.lstrip('#')
            lv = len(value)
            color =  tuple(int(value[i:i + lv // 3], 16) for i in range(0, lv, lv // 3))
            army_colors[int(player)]=color
            return redirect(f'/meximg/{player}')

        app.run(host="0.0.0.0",port=8080)


if __name__ == "__main__":
    main()


pass
