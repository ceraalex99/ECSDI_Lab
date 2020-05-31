# -*- coding: utf-8 -*-
"""
Created on Fri Dec 27 15:58:13 2013

Esqueleto de agente usando los servicios web de Flask

/comm es la entrada para la recepcion de mensajes del agente
/Stop es la entrada que para el agente

Tiene una funcion AgentBehavior1 que se lanza como un thread concurrente

Asume que el agente de registro esta en el puerto 9000

@author: javier
"""
import argparse
import random
import sys
from multiprocessing import Process, Queue
import socket

from rdflib import Namespace, Graph, Literal
from flask import Flask, request, render_template
from AgentUtil.ACLMessages import get_message_properties, build_message, send_message, get_agent_info

from AgentUtil.FlaskServer import shutdown_server
from AgentUtil.Agent import Agent
from AgentUtil.Logging import config_logger
from AgentUtil.OntoNamespaces import DSO, ECSDI, ACL
from rdflib.namespace import RDF, FOAF, XSD

__author__ = 'Miguel'

# Definimos los parametros de la linea de comandos
parser = argparse.ArgumentParser()
parser.add_argument('--open', help="Define si el servidor est abierto al exterior o no", action='store_true', default=False)
parser.add_argument('--port', type=int, help="Puerto de comunicacion del agente")
parser.add_argument('--dhost', default=socket.gethostname(), help="Host del agente de directorio")
parser.add_argument('--dport', type=int, help="Puerto de comunicacion del agente de directorio")

# parsing de los parametros de la linea de comandos
args = parser.parse_args()

# Configuration stuff
if args.port is None:
    port = 9031
else:
    port = args.port

if args.open is None:
    hostname = '0.0.0.0'
else:
    hostname = socket.gethostname()

if args.dport is None:
    dport = 9000
else:
    dport = args.dport

if args.dhost is None:
    dhostname = socket.gethostname()
else:
    dhostname = args.dhost

logger = config_logger(level=1)

agn = Namespace("http://www.agentes.org#")

# Contador de mensajes
mss_cnt = 0

# Datos del Agente

AgenteExternoTiendaExterna = Agent('AgenteExternoTiendaExterna',
                       agn.AgenteExternoTiendaExterna,
                       'http://%s:%d/comm' % (hostname, port),
                       'http://%s:%d/Stop' % (hostname, port))

# Directory agent address
AgenteDirectorio = Agent('AgenteDirectorio',
                       agn.AgenteDirectorio,
                       'http://%s:9000/Register' % hostname,
                       'http://%s:9000/Stop' % hostname)


# Global triplestore graph
dsgraph = Graph()

cola1 = Queue()

# Flask stuff
app = Flask(__name__, template_folder='../templates')

def get_count():
    global mss_cnt
    mss_cnt += 1
    return mss_cnt

def register():
    global mss_cnt
    logger.info("Nos registramos")
    gmess = Graph()
    gmess.bind('foaf', FOAF)
    gmess.bind('dso', DSO)
    reg_obj = agn[AgenteExternoTiendaExterna.name + '-Register']
    gmess.add((reg_obj, RDF.type, DSO.Register))
    gmess.add((reg_obj, DSO.Uri, AgenteExternoTiendaExterna.uri))
    gmess.add((reg_obj, FOAF.name, Literal(AgenteExternoTiendaExterna.name)))
    gmess.add((reg_obj, DSO.Address, Literal(AgenteExternoTiendaExterna.address)))
    gmess.add((reg_obj, DSO.AgentType, DSO.AgenteExternoTiendaExterna))

    gr = send_message(
        build_message(gmess, perf=ACL.request,
                      sender=AgenteExternoTiendaExterna.uri,
                      receiver=AgenteDirectorio.uri,
                      content=reg_obj,
                      msgcnt=mss_cnt),
        AgenteDirectorio.address)
    mss_cnt += 1

    return gr

@app.route("/")
def browser_root():
    return render_template('rootTiendaExterna.html')

@app.route("/registrarProducto", methods=['GET', 'POST'])
def browser_registrarProducto():
    """
    Permite la comunicacion con el agente via un navegador
    via un formulario
    """
    if request.method == 'GET':
        return render_template('registerProduct.html')
    else:
        nombre = request.form['nombre']
        marca = request.form['marca']
        modelo = request.form['modelo']
        precio = request.form['precio']
        peso = request.form['peso']

    content = ECSDI['Registra_productes_' + str(get_count())]

    gr = Graph()
    gr.add((content, RDF.type, ECSDI.Integrar_producto))

    sProdructo = ECSDI['Producto_' + str(random.randint(1, sys.float_info.max))]

    gr.add((sProdructo, RDF.type, ECSDI.Producto_externo))
    gr.add((sProdructo, ECSDI.Nombre, Literal(nombre, datatype=XSD.string)))
    gr.add((sProdructo, ECSDI.Marca, Literal(marca, datatype=XSD.string)))
    gr.add((sProdructo, ECSDI.Modelo, Literal(modelo, datatype=XSD.string)))
    gr.add((sProdructo, ECSDI.Precio, Literal(precio, datatype=XSD.float)))
    gr.add((sProdructo, ECSDI.Peso, Literal(peso, datatype=XSD.float)))

    gr.add((content, ECSDI.producto, sProdructo))

    agente = get_agent_info(agn.AgenteNegociadorTiendasExternas, AgenteDirectorio, AgenteExternoTiendaExterna, get_count())

    send_message(
        build_message(
            gr, perf=ACL.inform, sender=AgenteExternoTiendaExterna.uri, receiver=agente.uri, msgcnt=get_count(), content=content), agente.address)

    res = {'marca': request.form['marca'], 'nombre': request.form['nombre'], 'modelo': request.form['modelo'],
           'precio': request.form['precio'], 'peso': request.form['peso']}

    return render_template('producto.html', producto=res)

@app.route("/comm")
def comunicacion():
    """
    Communication Entrypoint
    """

    global dsGraph
    logger.info('Aviso a Tienda Externa de Compra Realizada')

    message = request.args['content']
    gm = Graph()
    gm.parse(data=message)

    msgdic = get_message_properties(gm)

    gr = None

    if msgdic is None:
        # Si no es, respondemos que no hemos entendido el mensaje
        gr = build_message(Graph(), ACL['not-understood'], sender=AgenteExternoTiendaExterna.uri, msgcnt=get_count())
    else:
        # El AgenteNegociadorTiendasExternas nos informa de que ha habido una compra de uno de nuestros productos
        if msgdic['performative'] != ACL.inform:
            gr = build_message(Graph(), ACL['not-understood'], sender=AgenteExternoTiendaExterna.uri, msgcnt=get_count())
        else:
            procesarCompra()


def procesarCompra():
    return 0

@app.route("/Stop")
def stop():
    """
    Entrypoint que para el agente

    :return:
    """
    tidyup()
    shutdown_server()
    return "Parando Servidor"


def tidyup():
    """
    Acciones previas a parar el agente

    """
    pass


def agentbehavior1(cola):
    """
    Un comportamiento del agente

    :return:
    """
    pass


def devolverPrecio(peso):
    g = Graph()
    transportista = ECSDI.Transportista

    precio = peso * 3
    g.add((transportista, RDF.Type, ECSDI.Transportista))
    g.add((transportista, ECSDI.Nombre, Literal('Pedro')))
    g.add((transportista, ECSDI.Precio, Literal(precio)))

    return g


if __name__ == '__main__':
    # Ponemos en marcha los behaviors
    ab1 = Process(target=agentbehavior1, args=(cola1,))
    ab1.start()

    # Ponemos en marcha el servidor
    app.run(host=hostname, port=port)

    # Esperamos a que acaben los behaviors
    ab1.join()
    print('The End')


