import requests
import json
import mysql.connector
import os
from getpass import getpass
from datetime import datetime
import logging

# Configuración de logging
logging.basicConfig(filename='factura_import.log', level=logging.INFO, 
                    format='%(asctime)s:%(levelname)s:%(message)s')

CONFIG_FILE = 'config.json'

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_config(config):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=4)

def configure_prestashop():
    config = load_config()
    prestashop_config = config.get('prestashop', {})

    prestashop_config['host'] = input(f"Host de la base de datos de PrestaShop [{prestashop_config.get('host', '')}]: ") or prestashop_config.get('host')
    prestashop_config['user'] = input(f"Usuario de la base de datos de PrestaShop [{prestashop_config.get('user', '')}]: ") or prestashop_config.get('user')
    prestashop_config['password'] = getpass(f"Contraseña de la base de datos de PrestaShop [{prestashop_config.get('password', '')}]: ") or prestashop_config.get('password')
    prestashop_config['database'] = input(f"Nombre de la base de datos de PrestaShop [{prestashop_config.get('database', '')}]: ") or prestashop_config.get('database')

    config['prestashop'] = prestashop_config
    save_config(config)
    print("Configuración de PrestaShop guardada.")

def configure_woocommerce():
    config = load_config()
    woocommerce_config = config.get('woocommerce', {})

    woocommerce_config['url'] = input(f"URL de WooCommerce [{woocommerce_config.get('url', '')}]: ") or woocommerce_config.get('url')
    woocommerce_config['consumer_key'] = input(f"Consumer Key de WooCommerce [{woocommerce_config.get('consumer_key', '')}]: ") or woocommerce_config.get('consumer_key')
    woocommerce_config['consumer_secret'] = getpass(f"Consumer Secret de WooCommerce [{woocommerce_config.get('consumer_secret', '')}]: ") or woocommerce_config.get('consumer_secret')

    config['woocommerce'] = woocommerce_config
    save_config(config)
    print("Configuración de WooCommerce guardada.")

def configure_facturascripts():
    config = load_config()
    facturascripts_config = config.get('facturascripts', {})

    facturascripts_config['api_url'] = input(f"URL de la API de FacturaScripts [{facturascripts_config.get('api_url', '')}]: ") or facturascripts_config.get('api_url')
    facturascripts_config['api_key'] = getpass(f"Clave API de FacturaScripts [{facturascripts_config.get('api_key', '')}]: ") or facturascripts_config.get('api_key')

    config['facturascripts'] = facturascripts_config
    save_config(config)
    print("Configuración de FacturaScripts guardada.")

def view_config():
    config = load_config()
    print(json.dumps(config, indent=4))

def export_invoices_from_prestashop(start_date, end_date):
    config = load_config()
    db_config = config.get('prestashop', {})

    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor(dictionary=True)
        query = ("SELECT * FROM ps_orders WHERE date_add BETWEEN %s AND %s")
        cursor.execute(query, (start_date, end_date))
        invoices = cursor.fetchall()
        cursor.close()
        conn.close()
        with open('invoices.json', 'w') as f:
            json.dump(invoices, f)
        logging.info("Facturas exportadas correctamente desde PrestaShop.")
        return True
    except mysql.connector.Error as err:
        logging.error(f"Error al exportar facturas: {err}")
        return False

def export_invoices_from_woocommerce(start_date, end_date):
    config = load_config()
    woocommerce_config = config.get('woocommerce', {})

    try:
        url = f"{woocommerce_config['url']}/wp-json/wc/v3/orders"
        params = {
            'after': f"{start_date}T00:00:00",
            'before': f"{end_date}T23:59:59",
            'consumer_key': woocommerce_config['consumer_key'],
            'consumer_secret': woocommerce_config['consumer_secret']
        }
        response = requests.get(url, params=params)
        response.raise_for_status()
        invoices = response.json()
        with open('invoices.json', 'w') as f:
            json.dump(invoices, f)
        logging.info("Facturas exportadas correctamente desde WooCommerce.")
        return True
    except requests.RequestException as err:
        logging.error(f"Error al exportar facturas desde WooCommerce: {err}")
        return False

def transform_invoice(prestashop_invoice):
    return {
        "customer_name": prestashop_invoice["customer_name"],
        "date": prestashop_invoice["date_add"],
        "items": [
            {
                "description": prestashop_invoice["product_name"],
                "quantity": prestashop_invoice["product_quantity"],
                "price": prestashop_invoice["product_price"]
            }
        ],
        "total": prestashop_invoice["total_paid"]
    }

def transform_woocommerce_invoice(woocommerce_invoice):
    return {
        "customer_name": woocommerce_invoice["billing"]["first_name"] + " " + woocommerce_invoice["billing"]["last_name"],
        "date": woocommerce_invoice["date_created"],
        "items": [
            {
                "description": item["name"],
                "quantity": item["quantity"],
                "price": item["price"]
            } for item in woocommerce_invoice["line_items"]
        ],
        "total": woocommerce_invoice["total"]
    }

def invoice_exists(api_url, api_key, invoice):
    try:
        response = requests.get(f"{api_url}/facturas", headers={
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }, params={'search': invoice["reference"]})
        if response.status_code == 200:
            invoices = response.json()
            return any(inv['reference'] == invoice["reference"] for inv in invoices)
        else:
            logging.error(f'Error al buscar factura: {response.text}')
            return False
    except requests.RequestException as e:
        logging.error(f"Error de conexión: {e}")
        return False

def get_or_create_customer(api_url, api_key, invoice):
    try:
        customer_name = invoice["customer_name"]
        response = requests.get(f"{api_url}/clientes", headers={
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }, params={'search': customer_name})

        if response.status_code == 200:
            customers = response.json()
            if customers:
                return customers[0]['id']
            else:
                customer_data = {
                    "name": customer_name,
                    "email": invoice["customer_email"],
                    "phone": invoice["customer_phone"]
                }
                create_response = requests.post(f"{api_url}/clientes", headers={
                    'Authorization': f'Bearer {api_key}',
                    'Content-Type': 'application/json'
                }, data=json.dumps(customer_data))

                if create_response.status_code == 201:
                    return create_response.json()['id']
                else:
                    logging.error(f'Error al crear cliente: {create_response.text}')
                    return None
        else:
            logging.error(f'Error al buscar cliente: {response.text}')
            return None
    except requests.RequestException as e:
        logging.error(f"Error de conexión: {e}")
        return None

def import_invoices_to_facturascripts():
    config = load_config()
    facturascripts_config = config.get('facturascripts', {})
    api_url = facturascripts_config.get('api_url')
    api_key = facturascripts_config.get('api_key')

    try:
        with open('invoices.json', 'r') as f:
            invoices = json.load(f)
    except FileNotFoundError:
        logging.error("El archivo invoices.json no se encontró.")
        return False

    for invoice in invoices:
        if "date_add" in invoice:  # Check if it's a PrestaShop invoice
            transformed_invoice = transform_invoice(invoice)
        else:  # Otherwise, treat it as a WooCommerce invoice
            transformed_invoice = transform_woocommerce_invoice(invoice)

        if not invoice_exists(api_url, api_key, transformed_invoice):
            customer_id = get_or_create_customer(api_url, api_key, transformed_invoice)
            if customer_id:
                transformed_invoice["customer_id"] = customer_id
                try:
                    response = requests.post(f"{api_url}/facturas", headers={
                        'Authorization': f'Bearer {api_key}',
                        'Content-Type': 'application/json'
                    }, data=json.dumps(transformed_invoice))

                    if response.status_code == 201:
                        logging.info(f'Factura importada correctamente.')
                    else:
                        logging.error(f'Error al importar factura: {response.text}')
                except requests.RequestException as e:
                    logging.error(f"Error de conexión: {e}")
            else:
                logging.error(f'Error al obtener o crear cliente para la factura.')
        else:
            logging.info(f'La factura ya existe y no se importará.')
    return True

def main_menu():
    while True:
        print("\nMenu:")
        print("1. Configurar conexión a PrestaShop")
        print("2. Configurar conexión a WooCommerce")
        print("3. Configurar conexión a FacturaScripts")
        print("4. Ver configuración actual")
        print("5. Exportar facturas desde PrestaShop")
        print("6. Exportar facturas desde WooCommerce")
        print("7. Importar facturas a FacturaScripts")
        print("8. Salir")

        choice = input("Seleccione una opción: ")

        if choice == '1':
            configure_prestashop()
        elif choice == '2':
            configure_woocommerce()
        elif choice == '3':
            configure_facturascripts()
        elif choice == '4':
            view_config()
        elif choice == '5':
            start_date = input("Ingrese la fecha de inicio (YYYY-MM-DD): ")
            end_date = input("Ingrese la fecha de fin (YYYY-MM-DD): ")
            if export_invoices_from_prestashop(start_date, end_date):
                print("Facturas exportadas correctamente desde PrestaShop.")
            else:
                print("Error al exportar facturas desde PrestaShop.")
        elif choice == '6':
            start_date = input("Ingrese la fecha de inicio (YYYY-MM-DD): ")
            end_date = input("Ingrese la fecha de fin (YYYY-MM-DD): ")
            if export_invoices_from_woocommerce(start_date, end_date):
                print("Facturas exportadas correctamente desde WooCommerce.")
            else:
                print("Error al exportar facturas desde WooCommerce.")
        elif choice == '7':
            if import_invoices_to_facturascripts():
                print("Facturas importadas correctamente a FacturaScripts.")
            else:
                print("Error al importar facturas a FacturaScripts.")
        elif choice == '8':
            break
        else:
            print("Opción no válida. Por favor, intente de nuevo.")

if __name__ == "__main__":
    main_menu()
