# -*- coding: iso-8859-1 -*-
"""
.. module:: RandomInfo

RandomInfo
*************

:Description: RandomInfo

    Genera un grafo RDF con aserciones generando los valores de los atributos aleatoriamente

    Asumimos que tenemos ya definida una ontologia y simplemente escogemos una o varias de las clases
    y generamos aleatoriamente los valores para sus atributos.

    Solo tenemos que a�adir aserciones al grafo RDFlib y despues grabarlo en OWL (o turtle), el resultado
    deberia poder cargarse en Protege, en un grafo RDFlib o en una triplestore (Stardog, Fuseki, ...)

    Se puede a�adir tambien aserciones sobre las clases y los atributos si no estan ya en una ontologia
      que hayamos elaborado con Protege

:Authors: bejar
    

:Version: 

:Created on: 22/04/2016 12:30 

"""

from rdflib import Graph, RDF, RDFS, OWL, XSD, Namespace, Literal
import string
import random

__author__ = 'bejar'

def random_name(prefix, size=6, chars=string.ascii_uppercase + string.digits):
    """
    Genera un nombre aleatorio a partir de un prefijo, una longitud y una lista con los caracteres a usar
    en el nombre
    :param prefix:
    :param size:
    :param chars:
    :return:
    """
    return prefix + '_' + ''.join(random.choice(chars) for _ in range(size))

def random_attribute(type, lim):
    """
    Genera un valor de atributo al azar dentro de un limite de valores para int y floar
    :param type:
    :return:
    """
    if len(lim) == 0 or lim[0] > lim[1]:
        raise Exception('No Limit')
    if type == 'f':
        return random.uniform(lim[0], lim[1])
    elif type == 'i':
        return int(random.uniform(lim[0], lim[1]))

if __name__ == '__main__':
    # Declaramos espacios de nombres de nuestra ontologia, al estilo DBPedia (clases, propiedades, recursos)
    PrOntPr = Namespace("http://www.semanticweb.org/migue/ontologies/2020/4/ecsdi-practica-ontologia/property/")
    PrOntRes = Namespace("http://www.semanticweb.org/migue/ontologies/2020/4/ecsdi-practica-ontologia/resource/")
    PrOnt = Namespace("http://www.semanticweb.org/migue/ontologies/2020/4/ecsdi-practica-ontologia/")


    # lista de tipos XSD datatypes para los rangos de las propiedades
    xsddatatypes = {'s': XSD.string, 'i': XSD.int, 'f': XSD.float}

    # Creamos instancias de la clase PrOnt.ElectronicDevice asumiendo que esta clase ya existe en nuestra ontologia
    # nos hace falta a�adirla al fichero de instancias si queremos usarla para hacer consultas sobre sus subclases
    #
    # Asumimos que tenemos los atributos
    #  * PrOntPr.tieneMarca: de producto a marca
    #  * PrOntPr.precio: real
    #  * PrOnt.peso: real
    #  * PrOntPr.nombre: string

    # Diccionario de atributos f= tipo float, i= tipo int, s= tipo string, otro => clase existente en la ontologia
    product_properties = {'marca': 'Marca',
                          'modelo': 'Modelo',
                          'precio': 'i',
                          'peso': 'f',
                          'nombre': 's'}

    # Diccionario con clases, cada clase tiene una lista con los atributos y en el caso de necesitarlo, su rango min/max
    product_classes = {'Movil': [['marca'],
                                 ['modelo'],
                                 ['precio', 50, 600],
                                 ['peso', 200,400],
                                 ['nombre']],
                       'Silla': [['marca'],
                                 ['modelo'],
                                 ['precio', 30, 200],
                                 ['peso', 4000, 20000],
                                 ['nombre']],
                       'Portatil': [['marca'],
                                    ['modelo'],
                                 ['precio', 450, 2000],
                                 ['peso', 1000, 2500],
                                 ['nombre']],
                       }

    products_graph = Graph()

    # A�adimos los espacios de nombres al grafo
    products_graph.bind('pont', PrOnt)


    # Clase padre de los productos
    products_graph.add((PrOnt.Producto, RDF.type, OWL.Class))

    # A�adimos los atributos al grafo con sus rangos (los dominios los a�adimos despues con cada clase)
    for prop in product_properties:
        if product_properties[prop] in ['s', 'i', 'f']:
            products_graph.add((PrOntPr[prop], RDF.type, OWL.DatatypeProperty))
            products_graph.add((PrOntPr[prop], RDFS.range, xsddatatypes[product_properties[prop]]))
        else:
            products_graph.add((PrOntPr[prop], RDF.type, OWL.ObjectProperty))
            products_graph.add((PrOntPr[prop], RDFS.range, PrOnt[product_properties[prop]]))


    # Clase de las marcas
    # Si tenemos ya generadas instancias para los rangos de relaciones
    # podemos consultarlas de un grafo RDF para usarlas como valores
    # En este ejemplo como solo hay una relacion generamos las instancias a mano y al azar
    products_graph.add((PrOnt.Marca, RDF.type, OWL.Class))

    for prc in product_classes:
        products_graph.add((PrOnt[prc], RDFS.subClassOf, PrOnt.Producto))

        # A�adimos las propiedades con sus dominios (si no estan ya en la definicion de la ontologia original)

        for prop in product_classes[prc]:
            products_graph.add((PrOntPr[prop[0]], RDFS.domain, PrOnt[prc]))

        # Generamos instancias de marcas al azar (nada impide que las marcas puedan ser comunes
        # entre productos (en este ejemplo no lo son)
        dclases = {'Marca': [], 'Modelo': []}
        for i in range(10):
            # instancia al azar
            rmarca = random_name('Marca_'+ prc)
            dclases['Marca'].append(rmarca)
            # A�adimos la instancia de marca
            products_graph.add((PrOntRes[rmarca], RDF.type, PrOnt.Marca))
            # Le asignamos una propiedad nombre a la marca
            products_graph.add((PrOntRes[rmarca], PrOntPr.nombre, Literal(rmarca)))

        for i in range(10):
            rmodelo = random_name('Modelo_' + prc)
            dclases['Modelo'].append(rmodelo)
            products_graph.add((PrOntRes[rmodelo], RDF.type, PrOnt.Modelo))
            products_graph.add((PrOntRes[rmodelo], PrOntPr.nombre, Literal(rmodelo)))



        # generamos instancias de productos
        for i in range(20):
            # instancia al azar
            rproduct = random_name(prc)
            products_graph.add((PrOntRes[rproduct], RDF.type, PrOnt[prc]))

            # Generamos sus atributos
            for attr in product_classes[prc]:
                prop = product_properties[attr[0]]
                # el atributo es real o entero
                if prop == 'f' or prop == 'i':
                    val = Literal(random_attribute(prop, attr[1:]))
                # el atributo es string
                elif prop == 's':
                    val = Literal(random_name(attr[0]))
                else:
                    val = PrOntRes[random.choice(dclases[prop])]
                products_graph.add((PrOntRes[rproduct], PrOntPr[attr[0]], val))


    # Resultado en Turtle
    print(products_graph.serialize(format='turtle'))


    # Grabamos el OWL resultante
    # Lo podemos cargar en Protege para verlo y cargarlo con RDFlib o en una triplestore (Stardog/Fuseki)
    ofile = open('../../data/product.owl', "wb")
    ofile.write(products_graph.serialize(format='turtle'))
    ofile.close()