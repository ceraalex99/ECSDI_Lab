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
import random
from multiprocessing import Process, Queue
import socket
import argparse
import sys

from rdflib import Namespace, Graph, Literal, URIRef
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
logger = config_logger(level=1)
if args.port is None:
    port = 9032
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

agn = Namespace("http://www.agentes.org#")

# Contador de mensajes
mss_cnt = 0

# Configuration constants and variables
agn = Namespace("http://www.agentes.org#")

# Datos del Agente
AgenteExternoAsistentePersonal = Agent('AgenteExternoAsistentePersonal',
                                       agn.AgenteExternoAsistentePersonal,
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

# Global dsgraph triplestore
dsgraph = Graph()

# Productos enconctrados
listaProductos = []

# Compras enconctrados
compras = []


def get_count():
    global mss_cnt
    mss_cnt += 1
    return mss_cnt

@app.route("/")
def browser_root():
    return render_template('rootAsistentePersonal.html')

@app.route("/buscar", methods=['GET', 'POST'])
def browserBucador():
    """
    Comunicacion con el agente mediante un formulario en un navegador
    """
    global listaProductos
    if request.method == 'GET':
        return render_template('buscador.html', productos=None)
    elif request.method == 'POST':
        #peticion de busqueda
        if request.form['submit'] == 'buscar':
            logger.info("Enviar peticion de busqueda")

            content = ECSDI['BuscarProductos_' + str(get_count())]

            gr = Graph()
            gr.add((content, RDF.type, ECSDI.Cerca_productes))

            modelo = request.form['modelo']
            if modelo:
                # Subject modelo
                sModelo = ECSDI['RestriccioModelo' + str(get_count())]
                gr.add((sModelo, RDF.type, ECSDI.RestriccioNom))
                gr.add((sModelo, ECSDI.Nom, Literal(modelo, datatype=XSD.string)))
                # Add restriccio to content
                gr.add((content, ECSDI.Restringe, URIRef(sModelo)))

            marca = request.form['marca']
            if marca:
                subject_marca = ECSDI['RestriccionMarca_' + str(get_count())]
                gr.add((subject_marca, RDF.type, ECSDI.Restriccion_Marca))
                gr.add((subject_marca, ECSDI.Marca, Literal(marca, datatype=XSD.string)))
                gr.add((content, ECSDI.Restringe, URIRef(subject_marca)))

            min_price = request.form['min_price']
            max_price = request.form['max_price']
            if min_price or max_price:
                sPreus = ECSDI['RestriccionPreus_' + str(get_count())]
                gr.add((sPreus, RDF.type, ECSDI.Rango_precio))
                if min_price:
                    gr.add((sPreus, ECSDI.Precio_min, Literal(min_price)))
                if max_price:
                    gr.add((sPreus, ECSDI.Precio_max, Literal(max_price)))
                gr.add((content, ECSDI.Restringe, URIRef(sPreus)))

            buscador = get_agent_info(agn.AgenteBuscador, AgenteDirectorio, AgenteExternoAsistentePersonal, get_count())

            gr2 = send_message(
                build_message(
                    gr, perf=ACL.request, sender=AgenteExternoAsistentePersonal.uri, receiver=buscador.uri, msgcnt=get_count(), content=content), buscador.address)

            index = 0
            # posicion del sujeto
            sPos = {}
            listaProductos = []
            for s, p, o in gr2:
                if s not in sPos:
                    sPos[s] = index
                    listaProductos.append({})
                    index += 1
                if s in sPos:
                    sDict = listaProductos[sPos[s]]
                    if p == RDF.type:
                        sDict['url'] = s
                    elif p == ECSDI.Marca:
                        sDict['marca'] = o
                    elif p == ECSDI.Modelo:
                        sDict['modelo'] = o
                    elif p == ECSDI.Precio:
                        sDict['precio'] = o
                    elif p == ECSDI.Nombre:
                        sDict['nombre'] = o
                    elif p == ECSDI.Peso:
                        sDict['peso'] = o
                    listaProductos[sPos[s]] = sDict

            return render_template('buscador.html', products=listaProductos)

        elif request.form['submit'] == 'Comprar':
            productosPedidos = []
            for producto in request.form.getlist("checkbox"):
                productoMarcado = []
                productosMap = listaProductos[int(producto)]
                productoMarcado.append(productosMap['marca'])
                productoMarcado.append(productosMap['modelo'])
                productoMarcado.append(productosMap['nombre'])
                productoMarcado.append(productosMap['precio'])
                productoMarcado.append(productosMap['url'])
                productoMarcado.append(productosMap['peso'])
                productosPedidos.append(productoMarcado)

            logger.info("Creando la peticion de compra")

            # Content of the message
            content = ECSDI['PeticionCompra_' + str(get_count())]

            # Graph creation
            gr = Graph()
            gr.add((content, RDF.type, ECSDI.PeticionCompra))

            # Asignar prioridad a la peticion (asignamos el contador de mensaje)
            gr.add((content, ECSDI.Prioridad, Literal(get_count(), datatype=XSD.integer)))

            # Creacion de la ciudad (por ahora Barcelona) --------------------------------------------------------------
            subject_ciudad = ECSDI['Ciudad_' + str(random.randint(1, sys.float_info.max))]

            gr.add((subject_ciudad, RDF.type, ECSDI.Ciudad))
            gr.add((subject_ciudad, ECSDI.Nombre, Literal(41.398373, datatype=XSD.float)))
            gr.add((subject_ciudad, ECSDI.Latitud, Literal(2.188247, datatype=XSD.float)))
            gr.add((subject_ciudad, ECSDI.Longitud, Literal('Barcelona', datatype=XSD.string)))

            # Creacion del sobre (Compra) ------------------------------------------------------------------------------
            sCompra = ECSDI['Compra_' + str(random.randint(1, sys.float_info.max))]
            gr.add((sCompra, RDF.type, ECSDI.Compra))

            gr.add((sCompra, ECSDI.Pagat, Literal(0, datatype=XSD.integer)))
            gr.add((sCompra, ECSDI.Enviar_a, URIRef(subject_ciudad)))

            totalPrice = 0.0
            for producto in productosPedidos:
                totalPrice += float(producto[3])
                # Creacion del producto --------------------------------------------------------------------------------
                sProducto = producto[4]
                gr.add((sProducto, RDF.type, ECSDI.Producto))
                gr.add((sProducto, ECSDI.Marca, Literal(producto[0], datatype=XSD.string)))
                gr.add((sProducto, ECSDI.Modelo, Literal(producto[1], datatype=XSD.string)))
                gr.add((sProducto, ECSDI.Nombre, Literal(producto[2], datatype=XSD.string)))
                gr.add((sProducto, ECSDI.Precio, Literal(producto[3], datatype=XSD.float)))
                gr.add((sProducto, ECSDI.Peso, Literal(producto[5], datatype=XSD.float)))
                gr.add((sCompra, ECSDI.Productos, URIRef(sProducto)))

            gr.add((sProducto, ECSDI.Precio_total, Literal(totalPrice, datatype=XSD.float)))
            gr.add((content, ECSDI.Sobre, URIRef(sCompra)))

            tienda = get_agent_info(agn.AgenteCompra, AgenteDirectorio, AgenteExternoAsistentePersonal, get_count())

            respuesta = send_message(
                build_message(
                    gr, perf=ACL.request, sender=AgenteExternoAsistentePersonal.uri, receiver=tienda.uri, msgcnt=get_count(), content=content), tienda.address)

            matrizProductos = []
            for item in respuesta.subjects(RDF.type, ECSDI.Producto):
                product = [respuesta.value(subject=item, predicate=ECSDI.Marca),
                           respuesta.value(subject=item, predicate=ECSDI.Modelo),
                           respuesta.value(subject=item, predicate=ECSDI.Nombre),
                           respuesta.value(subject=item, predicate=ECSDI.Precio)]
                matrizProductos.append(product)

            return render_template('finalCompra.html', products=matrizProductos)

@app.route("/retorna", methods=['GET', 'POST'])
def browserDevolucion():
    global compras
    if request.method == 'GET':
        logger.info('Se muestran todas las Compras')
        count, counts = getAllCompras()
        return render_template('devolucion.html', compras=compras, count=count, tam=counts)
    else:
        logger.info('Peticon de devolucion')
        comprasRealizadas = []
        for item in request.form.getlist("checkbox"):
            comprasRealizadas.append(compras[int(item)][0])
        g = Graph()
        content = ECSDI['PeticionDevolucion_' + str(get_count())]
        g.add((content, RDF.type, ECSDI.PeticionDevolucion))
        for producto in comprasRealizadas:
            g.add((content, ECSDI.DevolucionCompra, URIRef(producto)))

        tienda = get_agent_info(agn.SellerAgent, AgenteDirectorio, AgenteExternoAsistentePersonal, get_count())

        send_message(
            build_message(g, perf=ACL.request, sender=AgenteExternoAsistentePersonal.uri, receiver=tienda.uri,
                          msgcnt=get_count(),
                          content=content), tienda.address)

        return render_template('endRetorna.html')

@app.route("/comm")
def comunicacion():
    """
    Entrypoint de comunicacion
    """
    return None


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

def getAllCompras():
    # [0] = url / [1] = [{producte}] / [2] = precio_total
    global compras
    compras = []

    mayorCompra = 0
    counts = []

    gCompras = Graph()
    #!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
    gCompras.parse(open('../data/compras'), format='turtle')

    for compraUrl in gCompras.subjects(RDF.type, ECSDI.Compra):
        countCompras = 0
        compraUnica = [compraUrl]
        products = []
        for productUrl in gCompras.objects(subject=compraUrl, predicate=ECSDI.Productos):
            countCompras += 1
            products.append(gCompras.value(subject=productUrl, predicate=ECSDI.Nombre))
        compraUnica.append(products)
        for precio_total in gCompras.objects(subject=compraUrl, predicate=ECSDI.PrecioTotal):
            compraUnica.append(precio_total)
        compras.append(compraUnica)
        counts.append(countCompras)
        if countCompras > mayorCompra:
            biggest_sell = countCompras

    return mayorCompra, counts


if __name__ == '__main__':
    # Ponemos en marcha los behaviors
    ab1 = Process(target=agentbehavior1, args=(cola1,))
    ab1.start()

    # Ponemos en marcha el servidor
    app.run(host=hostname, port=port)

    # Esperamos a que acaben los behaviors
    ab1.join()
    print('The End')
