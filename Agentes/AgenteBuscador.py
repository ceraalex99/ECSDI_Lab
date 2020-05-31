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
import sys
from multiprocessing import Process, Queue
import socket

from rdflib import Namespace, Graph, Literal, XSD
from flask import Flask, request
from AgentUtil.ACLMessages import get_message_properties, build_message, send_message
from AgentUtil.Logging import config_logger
from AgentUtil.FlaskServer import shutdown_server
from AgentUtil.Agent import Agent
from AgentUtil.OntoNamespaces import DSO, ECSDI, ACL
from rdflib.namespace import RDF, FOAF

__author__ = 'javier'

logger = config_logger(level=1)


# Configuration stuff
hostname = socket.gethostname()
port = 9020

agn = Namespace("http://www.agentes.org#")

# Contador de mensajes
mss_cnt = 0

# Datos del Agente

AgenteBuscador = Agent('AgenteBuscador',
                       agn.AgenteBuscador,
                       'http://%s:%d/comm' % (hostname, port),
                       'http://%s:%d/Stop' % (hostname, port))

# Directory agent address
AgenteDirectorio = Agent('AgenteDirectorio',
                       agn.Directorio,
                       'http://%s:9000/Register' % hostname,
                       'http://%s:9000/Stop' % hostname)


# Global triplestore graph
dsgraph = Graph()

cola1 = Queue()

# Flask stuff
app = Flask(__name__)

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
    reg_obj = agn[AgenteBuscador.name + '-Register']
    gmess.add((reg_obj, RDF.type, DSO.Register))
    gmess.add((reg_obj, DSO.Uri, AgenteBuscador.uri))
    gmess.add((reg_obj, FOAF.name, Literal(AgenteBuscador.name)))
    gmess.add((reg_obj, DSO.Address, Literal(AgenteBuscador.address)))
    gmess.add((reg_obj, DSO.AgentType, DSO.AgenteBuscador))

    gr = send_message(
        build_message(gmess, perf=ACL.request,
                      sender=AgenteBuscador.uri,
                      receiver=AgenteDirectorio.uri,
                      content=reg_obj,
                      msgcnt=mss_cnt),
        AgenteDirectorio.address)
    mss_cnt += 1

    return gr


@app.route("/comm")
def comunicacion():
    logger.info("Peticion recibida")
    global mss_cnt
    global dsgraph

    message = request.args['content']
    gm = Graph()
    gm.parse(data=message)

    msgdic = get_message_properties(gm)

    gr = None

    if msgdic is None:
        gr = build_message(Graph(), ACL['not-understood'], sender=AgenteBuscador.uri, msgcnt=get_count())

    else:
        if msgdic['performative'] != ACL.request:
            gr = build_message(Graph(), ACL['not-understood'], sender=AgenteBuscador.uri, msgcnt=get_count())

        else:
            content = msgdic['content']
            accion = gm.value(subject=content, predicate=RDF.type)

            if accion == ECSDI.Mostrar_busqueda:
                restricciones = gm.objects(content, ECSDI.Restringe)
                restricciones_dict = {}
                for restriccion in restricciones:
                    if gm.value(subject=restriccion, predicate=RDF.type) == ECSDI.Restriccion_Marca:
                        marca = gm.value(subject=restriccion, predicate=ECSDI.Marca)
                        logger.info("Marca: "+marca)
                        restricciones_dict['marca'] = marca
                    elif gm.value(subject=restriccion, predicate=RDF.type) == ECSDI.Restriccion_Modelo:
                        modelo = gm.value(subject=restriccion, predicate=ECSDI.Modelo)
                        logger.info('Modelo: ' + modelo)
                        restricciones_dict['modelo'] = modelo
                    elif gm.value(subject=restriccion, predicate=RDF.type) == ECSDI.Restriccion_Precio:
                        precio_max = gm.value(subject=restriccion, predicate=ECSDI.Precio_max)
                        precio_min = gm.value(subject=restriccion, predicate=ECSDI.Precio_min)
                        if precio_min:
                            logger.info('Precio minimo: ' + precio_min)
                            restricciones_dict['precio_min'] = precio_min.toPython()
                        if precio_max:
                            logger.info('Precio maximo: ' + precio_max)
                            restricciones_dict['precio_max'] = precio_max.toPython()

                gr = buscarProductos(**restricciones_dict)
                gr = build_message(gr, perf=ACL['inform-done'], sender=AgenteBuscador.uri, msgcnt=get_count(), receiver=msgdic['sender'])

            else:
                gr = build_message(Graph(), ACL['not-understood'], sender=AgenteBuscador.uri, msgcnt=get_count())

    logger.info('Respondemos a la peticion')
    return gr.serialize(format='xml')


def buscarProductos(modelo=None, marca=None, precio_min=0.0, precio_max=sys.float_info.max):
    graph = Graph()
    ontologyFile= open('../data/productos')
    graph.parse(ontologyFile, format='turtle')

    modeloPresence = marcaPresence = False
    query = """
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
    PREFIX default: <http://www.semanticweb.org/migue/ontologies/2020/4/ecsdi-practica-ontologia#>
    
    SELECT DISTINCT ?producto ?nombre ?marca ?modelo ?precio
        where {
            { ?producto rdf:type default:Producto } .
            ?producto default:Nombre ?nombre .
            ?producto default:Marca ?marca .
            ?producto default:Modelo ?modelo .
            ?producto default:Precio ?precio .
            ?producto default:Peso ?peso .
            FILTER("""

    if modelo is not None:
        query += """str(?modelo) = '""" + modelo + """'"""
        modeloPresence = True

    if marca is not None:
        if modeloPresence:
            query += """ && """
        query += """str(?marca) = '""" + marca + """'"""
        marcaPresence = True

    if modeloPresence or marcaPresence:
        query += """ && """
    query += """?precio >= """ + str(precio_min)  + """ && ?precio <= """ + str(precio_max) + """ )} order by asc(UCASE(str(?nombre)))"""

    gquery = graph.query(query)
    res = Graph()
    res.bind('ECSDI', ECSDI)
    for prod in gquery:
        logger.debug(prod.nombre, prod.marca, prod.modelo, prod.precio)
        res.add((prod.producto, RDF.type, ECSDI.Producto))
        res.add((prod.producto, ECSDI.Nombre, Literal(prod.nombre, datatype=XSD.string)))
        res.add((prod.producto, ECSDI.Marca, Literal(prod.marca, datatype=XSD.string)))
        res.add((prod.producto, ECSDI.Modelo, Literal(prod.modelo, datatype=XSD.string)))
        res.add((prod.producto, ECSDI.Precio, Literal(prod.precio, datatype=XSD.float)))
    return res



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


if __name__ == '__main__':
    # Ponemos en marcha los behaviors
    ab1 = Process(target=agentbehavior1, args=(cola1,))

    # Ponemos en marcha el servidor
    app.run(host=hostname, port=port)

    # Esperamos a que acaben los behaviors
    ab1.join()
    print('The End')


