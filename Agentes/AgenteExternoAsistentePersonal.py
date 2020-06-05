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
from AgentUtil.ACLMessages import build_message, send_message, get_agent_info

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
def browserBuscador():
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
            gr.add((content, RDF.type, ECSDI.Buscar))

            modelo = request.form['modelo']
            if modelo:
                # Subject modelo
                sModelo = ECSDI['RestriccioModelo' + str(get_count())]
                gr.add((sModelo, RDF.type, ECSDI.Restriccion_Modelo))
                gr.add((sModelo, ECSDI.Modelo, Literal(modelo, datatype=XSD.string)))
                # Add restriccio to content
                gr.add((content, ECSDI.Restringe, URIRef(sModelo)))

            marca = request.form['marca']
            if marca:
                smarca = ECSDI['RestriccionMarca_' + str(get_count())]
                gr.add((smarca, RDF.type, ECSDI.Restriccion_Marca))
                gr.add((smarca, ECSDI.Marca, Literal(marca, datatype=XSD.string)))
                gr.add((content, ECSDI.Restringe, URIRef(smarca)))

            min_price = request.form['min_price']
            max_price = request.form['max_price']
            if min_price or max_price:
                sPrecio = ECSDI['RestriccionPrecio_' + str(get_count())]
                gr.add((sPrecio, RDF.type, ECSDI.Restriccion_Precio))
                if min_price:
                    gr.add((sPrecio, ECSDI.Precio_min, Literal(min_price)))
                if max_price:
                    gr.add((sPrecio, ECSDI.Precio_max, Literal(max_price)))
                gr.add((content, ECSDI.Restringe, URIRef(sPrecio)))

            buscador = get_agent_info(agn.AgenteBuscador, AgenteDirectorio, AgenteExternoAsistentePersonal, get_count())

            logger.info("He recibido la uri del buscador")
            gr2 = send_message(
                build_message(
                    gr, perf=ACL.request, sender=AgenteExternoAsistentePersonal.uri, receiver=buscador.uri, msgcnt=get_count(), content=content), buscador.address)

            logger.info("Todo feten con la llamada al buscador")
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

            logger.info(listaProductos)
            return render_template('buscador.html', products=listaProductos)

        elif request.form['submit'] == 'comprar':
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
            gr.add((content, RDF.type, ECSDI.Peticion_compra))

            tienda = get_agent_info(agn.AgenteCompras, AgenteDirectorio, AgenteExternoAsistentePersonal, get_count())

            # Creacion del sobre (Compra) ------------------------------------------------------------------------------
            subject_sobre = ECSDI['Compra_' + str(random.randint(1, sys.float_info.max))]
            gr.add((subject_sobre, RDF.type, ECSDI.Compra))

            total_price = 0.0
            total_peso = 0.0
            for item in productosPedidos:
                total_price += float(item[3])
                total_peso += float(item[5])
                # Creacion del producto --------------------------------------------------------------------------------
                subject_producto = item[4]
                gr.add((subject_producto, RDF.type, ECSDI.Producto))
                gr.add((subject_producto, ECSDI.Marca, Literal(item[0], datatype=XSD.string)))
                gr.add((subject_producto, ECSDI.Modelo, Literal(item[1], datatype=XSD.string)))
                gr.add((subject_producto, ECSDI.Nombre, Literal(item[2], datatype=XSD.string)))
                gr.add((subject_producto, ECSDI.Precio, Literal(item[3], datatype=XSD.float)))
                gr.add((subject_producto, ECSDI.Peso, Literal(item[5], datatype=XSD.float)))
                gr.add((subject_sobre, ECSDI.Productos, URIRef(subject_producto)))

            gr.add((subject_sobre, ECSDI.Precio_total, Literal(total_price, datatype=XSD.float)))

            gr.add((content, ECSDI.Sobre, URIRef(subject_sobre)))

            logger.info('Llego aqui1')

            send_message(build_message(gr, perf=ACL.request, sender=AgenteExternoAsistentePersonal.uri, receiver=tienda.uri,
                    msgcnt=get_count(), content=content), tienda.address)

            logger.info('Llego aqui2')

            # Graph creation
            gr = Graph()
            gr.add((content, RDF.type, ECSDI.Pedido))

            # Asignar prioridad a la peticion (asignamos el contador de mensaje)
            gr.add((content, ECSDI.Prioridad, Literal(request.form["prioridad"], datatype=XSD.string)))

            gr.add((content, ECSDI.Precio_total, Literal(total_price, datatype=XSD.float)))
            gr.add((content, ECSDI.Peso, Literal(total_peso, datatype=XSD.float)))



            logger.info('Llego aqui')
            respuesta = send_message(
                build_message(
                    gr, perf=ACL.request, sender=AgenteExternoAsistentePersonal.uri, receiver=tienda.uri, msgcnt=get_count(), content=content), tienda.address)

            subject = respuesta.value(predicate=RDF.type, object=ECSDI.Info_transporte)
            precio_transporte = respuesta.value(subject=subject, predicate=ECSDI.Precio)
            nombre_transportista = respuesta.value(subject=subject, predicate=ECSDI.Nombre_transportista)
            fecha_llegada = respuesta.value(subject=subject, predicate=ECSDI.Fecha_entrega)

            logger.info(precio_transporte)
            logger.info(nombre_transportista)
            logger.info('Aqui no llego ni de coña')

            if precio_transporte is not None:
                precio_transporte = precio_transporte.toPython()
                precio_transporte = round(precio_transporte, 2)

            return render_template('finalCompra.html', products= productosPedidos,fecha_llegada=fecha_llegada, precio_total= total_price,precio_transporte=precio_transporte, nombre_transportista= nombre_transportista)


@app.route("/devolucion", methods=['GET', 'POST'])
def browserDevolucion():
    global compras
    if request.method == 'GET':
        logger.info('Se muestran todas las Compras')
        count, counts = getAllCompras()
        return render_template('devolucion.html', compras=compras, count=count, tam=counts)
    else:
        logger.info('Peticon de devolucion')
        devoluciones = []
        for item in request.form.getlist("checkbox"):
            devoluciones.append(compras[int(item)][0])

        g = Graph()
        content = ECSDI['Devolver_producto_' + str(get_count())]
        g.add((content, RDF.type, ECSDI.Devolver_producto))

        for compra in devoluciones:
            g.add((compra, RDF.type, ECSDI.Compra))

        logger.info('AQUI SI')
        agenteDevoluciones = get_agent_info(agn.AgenteDevoluciones, AgenteDirectorio, AgenteExternoAsistentePersonal, get_count())
        logger.info('AQUI NO')

        gm = send_message(
            build_message(g, perf=ACL.request, sender=AgenteExternoAsistentePersonal.uri, receiver=agenteDevoluciones.uri,
                          msgcnt=get_count(),
                          content=content), agenteDevoluciones.address)

        subject = gm.value(predicate=RDF.type, object=ECSDI.Info_transporte)
        transportista = gm.value(subject=subject, predicate=ECSDI.Nombre_transportista)
        logger.info(transportista)
        return render_template('finalDevolucion.html', transportista=transportista)

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
    gCompras.parse(open('../data/productos_pedidos.owl'), format='turtle')

    for compraUrl in gCompras.subjects(RDF.type, ECSDI.Compra):
        countCompras = 0
        compraUnica = [compraUrl]
        products = []
        for productUrl in gCompras.objects(subject=compraUrl, predicate=ECSDI.Productos):
            countCompras += 1
            products.append(gCompras.value(subject=productUrl, predicate=ECSDI.Nombre))
        compraUnica.append(products)
        for precio_total in gCompras.objects(subject=compraUrl, predicate=ECSDI.Precio_total):
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
    app.run(host=hostname, port=port, debug=True)

    # Esperamos a que acaben los behaviors
    ab1.join()
    print('The End')
