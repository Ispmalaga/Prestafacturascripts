import tkinter as tk
from tkinter import ttk, messagebox
import requests
import json
import mysql.connector
from getpass import getpass
from datetime import datetime
import logging

# Configuración de logging
logging.basicConfig(filename='factura_import.log', level=logging.INFO, 
                    format='%(asctime)s:%(levelname)s:%(message)s')

def export_invoices_from_prestashop(db_config, start_date, end_date):
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

def import_invoices_to_facturascripts(api_url, api_key):
    try:
        with open('invoices.json', 'r') as f:
            invoices = json.load(f)
    except FileNotFoundError:
        logging.error("El archivo invoices.json no se encontró.")
        return False

    for invoice in invoices:
        if not invoice_exists(api_url, api_key, invoice):
            transformed_invoice = transform_invoice(invoice)
            customer_id = get_or_create_customer(api_url, api_key, invoice)
            if customer_id:
                transformed_invoice["customer_id"] = customer_id
                try:
                    response = requests.post(f"{api_url}/facturas", headers={
                        'Authorization': f'Bearer {api_key}',
                        'Content-Type': 'application/json'
                    }, data=json.dumps(transformed_invoice))

                    if response.status_code == 201:
                        logging.info(f'Factura {invoice["id_order"]} importada correctamente.')
                    else:
                        logging.error(f'Error al importar factura {invoice["id_order"]}: {response.text}')
                except requests.RequestException as e:
                    logging.error(f"Error de conexión: {e}")
            else:
                logging.error(f'Error al obtener o crear cliente para la factura {invoice["id_order"]}')
        else:
            logging.info(f'La factura {invoice["id_order"]} ya existe y no se importará.')
    return True

def configure_prestashop():
    db_config = {
        'host': prestashop_host_entry.get(),
        'user': prestashop_user_entry.get(),
        'password': prestashop_password_entry.get(),
        'database': prestashop_db_entry.get()
    }
    return db_config

def configure_facturascripts():
    api_url = facturascripts_url_entry.get()
    api_key = facturascripts_api_key_entry.get()
    return api_url, api_key

def export_invoices():
    db_config = configure_prestashop()
    start_date = start_date_entry.get()
    end_date = end_date_entry.get()
    if export_invoices_from_prestashop(db_config, start_date, end_date):
        messagebox.showinfo("Éxito", "Facturas exportadas correctamente desde PrestaShop.")
    else:
        messagebox.showerror("Error", "Error al exportar facturas desde PrestaShop.")

def import_invoices():
    api_url, api_key = configure_facturascripts()
    if import_invoices_to_facturascripts(api_url, api_key):
        messagebox.showinfo("Éxito", "Facturas importadas correctamente a FacturaScripts.")
    else:
        messagebox.showerror("Error", "Error al importar facturas a FacturaScripts.")

# Crear la interfaz gráfica con Tkinter
root = tk.Tk()
root.title("Importador de Facturas PrestaShop a FacturaScripts")

# Sección de configuración de PrestaShop
prestashop_frame = ttk.LabelFrame(root, text="Configuración PrestaShop")
prestashop_frame.grid(row=0, column=0, padx=10, pady=10, sticky="ew")

prestashop_host_label = ttk.Label(prestashop_frame, text="Host:")
prestashop_host_label.grid(row=0, column=0, padx=5, pady=5, sticky="e")
prestashop_host_entry = ttk.Entry(prestashop_frame)
prestashop_host_entry.grid(row=0, column=1, padx=5, pady=5, sticky="ew")

prestashop_user_label = ttk.Label(prestashop_frame, text="Usuario:")
prestashop_user_label.grid(row=1, column=0, padx=5, pady=5, sticky="e")
prestashop_user_entry = ttk.Entry(prestashop_frame)
prestashop_user_entry.grid(row=1, column=1, padx=5, pady=5, sticky="ew")

prestashop_password_label = ttk.Label(prestashop_frame, text="Contraseña:")
prestashop_password_label.grid(row=2, column=0, padx=5, pady=5, sticky="e")
prestashop_password_entry = ttk.Entry(prestashop_frame, show="*")
prestashop_password_entry.grid(row=2, column=1, padx=5, pady=5, sticky="ew")

prestashop_db_label = ttk.Label(prestashop_frame, text="Base de Datos:")
prestashop_db_label.grid(row=3, column=0, padx=5, pady=5, sticky="e")
prestashop_db_entry = ttk.Entry(prestashop_frame)
prestashop_db_entry.grid(row=3, column=1, padx=5, pady=5, sticky="ew")

# Sección de configuración de FacturaScripts
facturascripts_frame = ttk.LabelFrame(root, text="Configuración FacturaScripts")
facturascripts_frame.grid(row=1, column=0, padx=10, pady=10, sticky="ew")

facturascripts_url_label = ttk.Label(facturascripts_frame, text="URL API:")
facturascripts_url_label.grid(row=0, column=0, padx=5, pady=5, sticky="e")
facturascripts_url_entry = ttk.Entry(facturascripts_frame)
facturascripts_url_entry.grid(row=0, column=1, padx=5, pady=5, sticky="ew")

facturascripts_api_key_label = ttk.Label(facturascripts_frame, text="Clave API:")
facturascripts_api_key_label.grid(row=1, column=0, padx=5, pady=5, sticky="e")
facturascripts_api_key_entry = ttk.Entry(facturascripts_frame, show="*")
facturascripts_api_key_entry.grid(row=1, column=1, padx=5, pady=5, sticky="ew")

# Sección de rango de fechas
date_frame = ttk.LabelFrame(root, text="Rango de Fechas")
date_frame.grid(row=2, column=0, padx=10, pady=10, sticky="ew")

start_date_label = ttk.Label(date_frame, text="Fecha de Inicio (YYYY-MM-DD):")
start_date_label.grid(row=0, column=0, padx=5, pady=5, sticky="e")
start_date_entry = ttk.Entry(date_frame)
start_date_entry.grid(row=0, column=1, padx=5, pady=5, sticky="ew")

end_date_label = ttk.Label(date_frame, text="Fecha de Fin (YYYY-MM-DD):")
end_date_label.grid(row=1, column=0, padx=5, pady=5, sticky="e")
end_date_entry = ttk.Entry(date_frame)
end_date_entry.grid(row=1, column=1, padx=5, pady=5, sticky="ew")

# Botones de acción
action_frame = ttk.Frame(root)
action_frame.grid(row=3, column=0, padx=10, pady=10, sticky="ew")

export_button = ttk.Button(action_frame, text="Exportar Facturas", command=export_invoices)
export_button.grid(row=0, column=0, padx=5, pady=5)

import_button = ttk.Button(action_frame, text="Importar Facturas", command=import_invoices)
import_button.grid(row=0, column=1, padx=5, pady=5)

# Iniciar el bucle principal de Tkinter
root.mainloop()
