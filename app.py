from datetime import datetime
import os
import socket
from flask import Flask, abort, request, jsonify,render_template, send_file, send_from_directory
from werkzeug.utils import secure_filename
from google.cloud import vision
import re
from linebot.v3.messaging import (
    Configuration, 
    ApiClient, 
    MessagingApi, 
    ReplyMessageRequest
)
from linebot.v3.webhook import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.webhooks import (
    MessageEvent,
    TextMessageContent, 
    ImageMessageContent,
    PostbackEvent
)
from linebot.v3.messaging import (
    TextMessage,
    URIAction,
    QuickReply,
    QuickReplyItem,
    PushMessageRequest, TemplateMessage, PostbackAction, TemplateMessage, ButtonsTemplate, ImageMessage,
)
# from linebot.v3.messaging import(  Configuration, 
#     ApiClient, 
#     MessagingApi, 
#     ReplyMessageRequest)
# from linebot.v3.webhook import WebhookHandler
# from linebot.v3.exceptions import InvalidSignatureError
# from linebot.v3.models import (
#      TextMessageContent, 
#     ImageMessageContent, 
#     Event,
#     QuickReply,
#     QuickReplyItem,
#     URIAction
# )

# import warnings
# from linebot import LineBotSdkDeprecatedIn30

# from linebot import LineBotApi, WebhookHandler
# from linebot.exceptions import InvalidSignatureError
# from linebot.models import MessageEvent, TextMessage, ImageMessage, TextSendMessage,TemplateSendMessage, ButtonsTemplate, URIAction, PostbackAction,PostbackEvent  
import mysql.connector
from mysql.connector import Error
import base64
from io import BytesIO
from PIL import Image
import uuid
import mimetypes


# Initialize Flask app
app = Flask(__name__ )
# Get the directory where app.py is located
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Define and create the uploads folder
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Define and create the signature folder
UPLOAD_SIGNATURE_FOLDER = os.path.join(BASE_DIR, 'signature')
os.makedirs(UPLOAD_SIGNATURE_FOLDER, exist_ok=True)
app.config['UPLOAD_SIGNATURE_FOLDER'] = UPLOAD_SIGNATURE_FOLDER

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

# check port running
def is_port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', port)) == 0

# Route สำหรับเสิร์ฟไฟล์รูปภาพจาก uploads
@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/signature/<filename>')
def signature_file(filename):
    return send_from_directory(app.config['UPLOAD_SIGNATURE_FOLDER'], filename)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def connect_to_database():
    """เชื่อมต่อกับฐานข้อมูล MySQL"""
    try:
        connection = mysql.connector.connect(
            host='localhost',
            user='ocr',
            password='oldk@ocr',
            database='ocrproject',
            # port=3306,
            port=59541,
        )
        if connection.is_connected():
            return connection
    except Error as e:
        print(f"เกิดข้อผิดพลาดในการเชื่อมต่อฐานข้อมูล: {e}")
        return None

def save_to_database(  recipient_name,student_id, room_number, tracking_number,note, filepath,signaturefilepath,sender):
    """บันทึกข้อมูลลงฐานข้อมูล"""
    try:
        connection = connect_to_database()
        cursor = connection.cursor()
        now = datetime.now()
        query = """
            INSERT INTO parcel (recipient_name, delivery_date, student_id, room_number,note, image_path,signature,sender_type,track_no)
            VALUES (%s, %s, %s, %s,%s, %s, %s, %s,%s)
        """
        values = (
            recipient_name,
            now,
            student_id,
            room_number,
            note,
            filepath,
            signaturefilepath,
            sender,
            tracking_number
        )
        cursor.execute(query, values)
        connection.commit()
        print(f"บันทึกข้อมูลสำเร็จ: {recipient_name}, {room_number}, {tracking_number}")
        return cursor.lastrowid
    except Error as e:
        print(f"เกิดข้อผิดพลาดในการบันทึกข้อมูลลงฐานข้อมูล: {e}")
        return None

@app.route('/')
def index():
    return render_template('form.html') 
    
@app.route('/submit', methods=['POST'])
def submit():
    # Get data from the AJAX request
    data = request.json
    if not data or 'student_id' not in data or 'line_uid' not in data:
        return jsonify({"message": "Invalid input data."}), 400

    try:
        connection = connect_to_database()
        if connection:
            cursor = connection.cursor()
            # Check if student_id exists in the database
            cursor.execute("SELECT * FROM students WHERE student_id = %s", (data['student_id'],))
            result = cursor.fetchone()
            if result:
                # Update line_id for the student
                cursor.execute("UPDATE students SET line_id = %s WHERE id = %s", (data['line_uid'], result[0]))
                connection.commit()
                return jsonify({"message": "Form submitted successfully! Now you can close the window."})
            else:
                return jsonify({"message": "Student not found."}), 400
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"message": "Failed to submit data due to server error."}), 500
    finally:
        if connection:
            connection.close()

@app.route('/upload_form', methods=['GET'])
def upload_form():
    return render_template('upload_form.html')

@app.route('/qr_scan', methods=['GET'])
def qrscan():
    return render_template('qrscan.html')
@app.route('/get_parcel', methods=['POST'])
def get_parcel():
    data = request.json
    if data:
        if data['line_user_id'] is None or data['line_user_id'] == "":
            print("Line user ID is required.")
            return jsonify({"message": "Line user ID is required."}), 400
        connection = connect_to_database()
        if connection:
            cursor = connection.cursor()
            cursor.execute(f"SELECT * FROM parcel WHERE track_no = '{data['tracking_no']}' AND status = 'Pending'")
            result = cursor.fetchone()
            if result:
                print(f"Parcel found: {result}")
                print(f"students: {result[4]}")
                if result[4] != 0:
                     line_user_id = data['line_user_id']
                     cursor.execute(f"SELECT * FROM students WHERE id = {result[4]} AND line_id = '{line_user_id}'")
                     student = cursor.fetchone()
                     print(f"Student: {line_user_id}")
                     if student:
                            # update status to Confirm
                            cursor.execute(f"UPDATE parcel SET status = 'Confirm' WHERE id = {result[0]}")
                            connection.commit()
                            # send message to the student
                            line_bot_api_2.push_message(
                                PushMessageRequest(
                                    to=line_user_id,
                                    messages=[
                                        TextMessage(text=" มีการยืนยันการรับพัสดุของคุณ")
                                    ]
                                ) )
                            return jsonify({"message": "Parcel found!", "data": result})
                     else:
                            return jsonify({"message": "Student not found or maybe it not your item."}), 400
                     

                # update status to Confirm
                return jsonify({"message": "Parcel found!", "data": result})
            else:
                return jsonify({"message": "Parcel not found."}), 400
    return jsonify({"message": "Failed to get parcel data."}), 400
    
@app.route('/upload', methods=['POST'])
def upload():
    try:
        # ตรวจสอบไฟล์ที่อัปโหลด
        if 'images[]' not in request.files:
            return jsonify({"message": "กรุณาอัปโหลดไฟล์รูปภาพ"}), 400
        
        # ตรวจสอบประเภทขนส่ง
        delivery_type = request.form.get('deliveryType')
        if not delivery_type:
            return jsonify({"message": "กรุณาเลือกประเภทขนส่ง"}), 400

        # ตรวจสอบลายเซ็น
        signature = request.form.get('signature')
        if not signature:
            return jsonify({"message": "กรุณาเพิ่มลายเซ็น"}), 400

        # บันทึกไฟล์รูปภาพ
        files = request.files.getlist('images[]')
        for file in files:
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)

        # บันทึกลายเซ็น Base64 เป็นไฟล์
        import base64
        from io import BytesIO
        from PIL import Image

        signature_data = signature.replace('data:image/png;base64,', '')
        image_data = base64.b64decode(signature_data)
        signature_image = Image.open(BytesIO(image_data))
        signature_path = os.path.join(app.config['UPLOAD_SIGNATURE_FOLDER'], "signature.png")
        signature_image.save(signature_path, "PNG")

        return jsonify({"message": "อัปโหลดข้อมูลสำเร็จ"}), 200

    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"message": "เกิดข้อผิดพลาดในเซิร์ฟเวอร์"}), 500

    sender = request.form.get('deliveryType')
   
    for file in files:
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            # use ocr to extract text from image
            with open(filepath, 'rb') as image_file:
              image_content = image_file.read()
            print(f"File uploaded: {filepath}")
            uploaded_files.append(filename)
            text = extract_text_from_image(image_content)
            if text:
                recipient_name, room_number, tracking_number = process_text(text)
                # room_number=1326
                if room_number != "Not found":
                    # search for students from the database
                    connection = connect_to_database()
                    if connection:
                        cursor = connection.cursor()
                        cursor.execute(f"SELECT * FROM students WHERE room_number = '{room_number}'")
                        result = cursor.fetchall()
                        print(f"Result: {result}")
                        if result:
                            # loop result and send message to each student
                            for student in result:
                                pkid=save_to_database( recipient_name,student[0], room_number, tracking_number,'', filename,signaturename,sender)
                                endpoint = f"https://oldk.duckdns.org/api/uploads/{filename}"
                                if student[5] is not None:
                                    line_bot_api_2.push_message(
                                            PushMessageRequest(
                                                to=student[5],
                                                # to=noti,
                                                messages=[
                                                    TemplateMessage(
                                                        alt_text='Package Received',
                                                        template=ButtonsTemplate(
                                                            title='พัสดุถึงแล้ว',
                                                            text=f'พัสดุหมายเลข: {pkid}\nกรุณายืนยันการรับพัสดุ',
                                                            actions=[
                                                                PostbackAction(
                                                                    label='รับพัสดุ',
                                                                    display_text='รับพัสดุ',
                                                                    data=f'action=receive&tracking={pkid}'
                                                                ),
                                                                PostbackAction(
                                                                    label='ไม่รับพัสดุ',
                                                                    display_text='ไม่รับพัสดุ',
                                                                    data=f'action=reject&tracking={pkid}'
                                                                )
                                                            ]
                                                        )
                                                    )
                                                ]
                                            )
                                        )
                                    line_bot_api_2.push_message(PushMessageRequest(
                                    to=student[5],
                                    messages=[
                                        ImageMessage(
                                            original_content_url=endpoint,
                                            preview_image_url=endpoint
                                        )
                                    ]
                                ))
                            # pkid=save_to_database( recipient_name,result[0], room_number, tracking_number,'', filename,signaturename,sender)
                            # line_bot_api_2.push_message(
                            #             PushMessageRequest(
                            #                 to=result[5],
                            #                 # to=noti,
                            #                 messages=[
                            #                     TemplateMessage(
                            #                         alt_text='Package Received',
                            #                         template=ButtonsTemplate(
                            #                             title='พัสดุถึงแล้ว',
                            #                             text=f'พัสดุหมายเลข: {pkid}\nกรุณายืนยันการรับพัสดุ',
                            #                             actions=[
                            #                                 PostbackAction(
                            #                                     label='รับพัสดุ',
                            #                                     display_text='รับพัสดุ',
                            #                                     data=f'action=receive&tracking={pkid}'
                            #                                 ),
                            #                                 PostbackAction(
                            #                                     label='ไม่รับพัสดุ',
                            #                                     display_text='ไม่รับพัสดุ',
                            #                                     data=f'action=reject&tracking={pkid}'
                            #                                 )
                            #                             ]
                            #                         )
                            #                     )
                            #                 ]
                            #             )
                            #         )
                            # # send img to line
                            # endpoint = f"https://oldk.duckdns.org/api/uploads/{filename}"
                            # line_bot_api_2.push_message(PushMessageRequest(
                            #     to=result[5],
                            #     messages=[
                            #         ImageMessage(
                            #             original_content_url=endpoint,
                            #             preview_image_url=endpoint
                            #         )
                            #     ]
                            # ))
                        else:
                            print(f"Student not found for room number: {room_number}")
                
                elif recipient_name != "Not found":
                    print(f"Recipient: {recipient_name}")
                    connection = connect_to_database()
                    if connection:
                        cursor = connection.cursor()
                        # remove นาง, นางสาว, นาย from the recipient name
                        recipient_name = recipient_name.replace("นางสาว", "").replace("นาง", "").replace("นาย", "").strip()
                        cursor.execute(f"SELECT * FROM students WHERE first_name = '{recipient_name}'")
                        result = cursor.fetchone()
                        if result:
                            # send message to the student
                            print(f"Student found for recipient name: {recipient_name}")
                            pkid=save_to_database( recipient_name,result[0], room_number, tracking_number,'', filename,signaturename,sender)
                            # noti='U644b501864125e7ab0b04eb47896ca3a'
                            if result[5] is not None:
                                line_bot_api_2.push_message(
                                            PushMessageRequest(
                                                to=result[5],
                                                # to=noti,
                                                messages=[
                                                    TemplateMessage(
                                                        alt_text='Package Received',
                                                        template=ButtonsTemplate(
                                                            title='พัสดุถึงแล้ว',
                                                            text=f'พัสดุหมายเลข: {pkid}\nกรุณายืนยันการรับพัสดุ',
                                                            actions=[
                                                                PostbackAction(
                                                                    label='รับพัสดุ',
                                                                    display_text='รับพัสดุ',
                                                                    data=f'action=receive&tracking={pkid}'
                                                                )
                                                            ]
                                                        )
                                                    )
                                                ]
                                            )
                                        )
                                # send img to line
                                endpoint = f"https://oldk.duckdns.org/api/uploads/{filename}"
                                line_bot_api_2.push_message(PushMessageRequest(
                                to=result[5],
                                messages=[
                                    ImageMessage(
                                        original_content_url=endpoint,
                                        preview_image_url=endpoint
                                    )
                                ]
                            ))
                        else:
                            print(f"Student not found for recipient name: {recipient_name}")
                # print(f"Recipient: {recipient_name}")
                # print(f"Room number: {room_number}")
                # print(f"Tracking number: {tracking_number}")
                else:
                    print("No recipient name or room number found in the text")
                    pkid=save_to_database( recipient_name,0, room_number, tracking_number,'ระบบไม่พบรายชื่อในระบบ', filename,signaturename,sender)              
    if uploaded_files:
        return jsonify({"message": "Files uploaded successfully!", "files": uploaded_files})
    else:
        return jsonify({"message": "No valid files uploaded."}), 400

@app.route('/uploads/<path:name>')
def serve_uploaded_file(name):
    # Serve the uploaded file
    return send_from_directory(
        app.config['UPLOAD_FOLDER'], name, as_attachment=False
    )

        # get all parcel
@app.route('/total')
def parcel_total():
    return render_template('total.html') 

@app.route('/api/parceltotal', methods=['GET'])
def get_parceltotal():
    try:
        # สร้างการเชื่อมต่อกับฐานข้อมูลโดยใช้ฟังก์ชัน connect_to_database()
        conn = connect_to_database()
        if not conn:
            return jsonify({"error": "Failed to connect to the database"}), 500

        print("Connection successful")
        cursor = conn.cursor(dictionary=True)

        # SQL Query
        query = """
        SELECT  
            parcel.recipient_name,
            parcel.id,
            parcel.student_id,
            parcel.created_at, 
            parcel.note,
            parcel.track_no, 
            parcel.sender_type, 
            parcel.image_path,
            parcel.status, 
            parcel.signature,
            students.first_name, 
            students.last_name,
            students.room_number
        FROM parcel
        INNER JOIN students 
            ON parcel.recipient_name COLLATE utf8mb4_general_ci = students.first_name COLLATE utf8mb4_general_ci;
        """
        cursor.execute(query)

        # ดึงข้อมูลจากฐานข้อมูล
        data = cursor.fetchall()

        # ปิดการเชื่อมต่อฐานข้อมูล
        cursor.close()
        conn.close()

        return jsonify(data)

    except Exception as err:
        return jsonify({"error": str(err)}), 500
        
@app.route('/update_parcel_status', methods=['POST'])
def update_parcel_status():
    try:
        # รับข้อมูล JSON
        data = request.get_json()
        parcel_id = data.get('parcel_id')

        if not parcel_id:
            return jsonify({'error': 'No parcel_id provided'}), 400

        # สร้างการเชื่อมต่อกับฐานข้อมูลโดยใช้ฟังก์ชัน connect_to_database()
        connection = connect_to_database()
        if not connection:
            return jsonify({"error": "Failed to connect to the database"}), 500

        cursor = connection.cursor()

        # SQL Query สำหรับอัพเดทสถานะ
        update_query = """
        UPDATE parcel
        SET status = 'Received',
            updated_at = CURRENT_TIMESTAMP
        WHERE id = %s
        """
        cursor.execute(update_query, (parcel_id,))
        connection.commit()

        # ตรวจสอบว่ามีการอัพเดทจริงหรือไม่
        if cursor.rowcount == 0:
            return jsonify({'error': 'Parcel not found'}), 404

        return jsonify({
            'success': True,
            'message': f'Updated status for parcel {parcel_id}'
        })

    except Exception as e:
        return jsonify({'error': 'Server error', 'message': str(e)}), 500

    finally:
        # ปิดการเชื่อมต่อฐานข้อมูล
        if 'cursor' in locals(): cursor.close()
        if 'connection' in locals(): connection.close()

@app.route('/parcelstuck') 
def stuck_parcel_page(): 
    return render_template('parcelstuck.html')

@app.route('/Yparcelstuck') 
def yesterday_stuck_parcel_page(): 
    return render_template('Yparcelstuck.html')
@app.route('/api/parcelstuck', methods=['GET'])
def get_parcelstuck():
    try:
        # เชื่อมต่อฐานข้อมูลด้วยฟังก์ชัน connect_to_database()
        conn = connect_to_database()
        if not conn:
            return jsonify({"error": "Failed to connect to the database"}), 500

        print("Connection successful")
        cursor = conn.cursor(dictionary=True)

        # คำสั่ง SQL เพื่อดึงข้อมูลพัสดุที่ไม่มีอยู่ในตาราง students
        query = """
        SELECT  
            parcel.id,
            parcel.recipient_name,
            parcel.created_at, 
            parcel.note,
            parcel.track_no,
            parcel.sender_type,
            parcel.image_path,
            parcel.status,
            parcel.signature
        FROM parcel
        WHERE parcel.status = 'Pending'
          AND NOT EXISTS (
              SELECT 1 
              FROM students 
              WHERE students.first_name COLLATE utf8mb4_general_ci = parcel.recipient_name COLLATE utf8mb4_general_ci
          );
        """
        cursor.execute(query)

        # ดึงข้อมูลจากฐานข้อมูล
        data = cursor.fetchall()

        # ปิดการเชื่อมต่อฐานข้อมูล
        cursor.close()
        conn.close()

        # ส่งข้อมูลกลับในรูปแบบ JSON
        return jsonify(data)

    except Exception as err:
        # จัดการข้อผิดพลาดและส่ง JSON กลับ
        return jsonify({"error": str(err)}), 500


   
@app.route('/get_parcels', methods=['GET'])
def get_parcels():
    connection = connect_to_database()
    if connection:
        cursor = connection.cursor(dictionary=True)  # Use dictionary cursor for associative array-like results
        cursor.execute("SELECT * FROM parcel")
        result = cursor.fetchall()
        return jsonify(result)
    return jsonify([])
@app.route('/signature/<path:name>')
def serve_signature_file(name):
    return send_from_directory(
        app.config['UPLOAD_SIGNATURE_FOLDER'], name, as_attachment=False
    )
    # return render_template('upload_form.html')

# student_history
@app.route('/student_history')  
def student_history():         
    student_id = request.args.get('id')
    if not student_id:
        return "Student ID is required!", 400
    return render_template('student_history.html', student_id=student_id)

@app.route('/api/parcels/<student_id>', methods=['GET'])
def get_parcel_data(student_id):
    try:
        # สร้างการเชื่อมต่อกับฐานข้อมูล
        connection = connect_to_database()
        cursor = connection.cursor(dictionary=True)  # ใช้ dictionary=True เพื่อดึงข้อมูลเป็น dict
        
        # ดึงข้อมูลพัสดุจากฐานข้อมูล
        cursor.execute("""
            SELECT * FROM parcel WHERE student_id = %s ORDER BY created_at DESC
        """, (student_id,))
        parcels = cursor.fetchall()

        # ตรวจสอบว่ามีข้อมูลหรือไม่
        if not parcels:
            app.logger.warning("Student ID is missing in the request.")
            return jsonify({'message': f'ไม่พบพัสดุสำหรับรหัสนักศึกษา: {student_id}', 'parcels': []}), 404

        # Format วันที่ให้เป็น ISO 8601
        for parcel in parcels:
            if 'created_at' in parcel and parcel['created_at']:
                parcel['created_at'] = parcel['created_at'].isoformat()

        # ส่งข้อมูลกลับไปเป็น JSON
        return jsonify({'student_id': student_id, 'parcels': parcels})

    except mysql.connector.Error as e:
        app.logger.error(f"Database error: {str(e)}")
        return jsonify({'error': f'Database error: {str(e)}'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        # ปิดการเชื่อมต่อฐานข้อมูล
        if 'cursor' in locals():
            cursor.close()
        if 'connection' in locals():
            connection.close()

            
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] =os.path.join(BASE_DIR, 'key.json')
configuration = Configuration()
configuration2 = Configuration()

# LINE API configuration
LINE_CHANNEL_ACCESS_TOKEN = 'DP+mMgEFOBKbnF8WnQFYTnDsSJrLFonKEHYnhXA05plvVyTg+O2eBm6+w+y4BtjuOST5SbP801W1JmIC7cj4K4mME1ixgfu/0RlDc/afTsol2uQw50uzhEm3/vq5EMt9VsKDS6ZvKhOOzknZgI/JswdB04t89/1O/w1cDnyilFU='
LINE_CHANNEL_SECRET = '77c920ae9c7fd30d0435b5da706f7eb2'
configuration.access_token = LINE_CHANNEL_ACCESS_TOKEN

# line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
#  = ApiClient(LINE_CHANNEL_ACCESS_TOKEN)
api_client = ApiClient(configuration)
line_bot_api= MessagingApi(api_client)
handler = WebhookHandler(LINE_CHANNEL_SECRET)
# LINE Bot นศ
# LINE_CHANNEL_ACCESS_TOKEN_2 = "RggR89/53DvKmLEPQbZxA8/xHprsxJ5XJY4DAybrfihHerURTMDGMisGKEoRSc3lWGbsysslHYMYGHaJ0qsmeVp/evYZQguBj+jm60waOSlJ48Ke06MmrnnNwpW1fzuNdavTX9OYdCLbFc6g0W9MrgdB04t89/1O/w1cDnyilFU="
# LINE_CHANNEL_SECRET_2 = "ddc85b7612055418ae9d7544436a832e"
LINE_CHANNEL_ACCESS_TOKEN_2 = "+Ze44nH3kOsZULviBCcklnvrA/OYAwvTzd3uNHJKwbYmmfE/SkEfq7r4o8r/2agcH43PPXfY69NADu2AY8KJhENP/dK6mVT8T9PgysAz9yvJWHcMo/7WDYIRVPzfFtMtn/GRRY2KmrE6MNEsb+HUcgdB04t89/1O/w1cDnyilFU="
LINE_CHANNEL_SECRET_2 = "ce777bc9f3f16466da880c30baf15802"
configuration2.access_token = LINE_CHANNEL_ACCESS_TOKEN_2
# line_bot_api_2 = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN_2)
api_client_2 = ApiClient(configuration2)
line_bot_api_2 = MessagingApi(api_client_2)
handler_2 = WebhookHandler(LINE_CHANNEL_SECRET_2)

# เรียกใช้ฟังก์ชัน
def send_line_notification(message):
    try:
        # ส่งข้อความแจ้งเตือนไปยังผู้ใช้
        line_bot_api.push_message(
            'source.user_id',  # User ID หรือ Group ID ที่ต้องการส่งข้อความ
            TextSendMessage(text=message)
        )
        print("Notification sent successfully")
    except Exception as e:
        print("Failed to send notification:", e)

# ตรวจสอบพัสดุและส่งแจ้งเตือน
def check_parcels_and_notify(parcels):
    # กรองข้อมูลพัสดุที่ไม่พบ
    filtered_parcels = [parcel for parcel in parcels if parcel['recipient_name'] == 'Not found']
    
    if filtered_parcels:
        # ส่งแจ้งเตือนเมื่อพบพัสดุตกค้าง
        message = "ตรวจพบพัสดุตกค้าง: จำนวน {} ชิ้น".format(len(filtered_parcels))
        send_line_notification(message)
    else:
        print("No pending parcels found")
def extract_text_from_image(image_content):
    """Extract text from an image."""
    try:
        client = vision.ImageAnnotatorClient()
        image = vision.Image(content=image_content)
        response = client.text_detection(image=image)
        
        if response.error.message:
            raise Exception(response.error.message)

        if response.text_annotations:
            return response.text_annotations[0].description
        return ""
        
    except Exception as e:
        print(f"Error reading image: {e}")
        return ""

def process_text(text):
    """Extract recipient name, room number, and tracking number from text."""
    recipient_name = "Not found"
    room_number = "Not found"
    tracking_number = "Not found"

    
    print("\nข้อความที่อ่านได้:")
    print(text)
    print("-" * 50)

    # ทำความสะอาดข้อความ
    cleaned_text = text.replace(" ", "").upper()
    
    # รูปแบบเลขพัสดุแยกตามความสำคัญ
    track_patterns = [
        # รูปแบบพิเศษ
        r'SPXTH\d{11}[A-Z]',
        r'LEXPU\d{10}',
        r'TH\d{5}F\d?[A-Z0-9]{4}\d{2}\b',
        r'TH\d{5}[A-Z][A-Z0-9]{4}[A-Z0-9][A-Z]\d',
        r'TH\d{5}[A-Z][A-Z0-9]{3}[A-Z][A-Z0-9]{2}\d',
        r'THT\d{8}[A-Z0-9]\d{2}\b',
        r'TH\d{12}[A-Z]',
        
        # รูปแบบ 12 หลัก
        r'(?:753|731)\d{9}\b',
        
        # รูปแบบทั่วไป
        r'TH[0-9A-Z]{14}',
        r'THT[0-9A-Z]{12}',
        r'TH\d{12}[A-Z]',
        r'TH\d{13}',
        r'FL\d{11}',
        r'JT\d{12}',
    ]
    
    # ค้นหาเลขพัสดุ โดยเน้นความแม่นยำ
    for pattern in track_patterns:
        matches = re.finditer(pattern, cleaned_text)
        for match in matches:
            potential_tracking = match.group(0)
            # กรณี รูปแบบ 12 หลัก จะมีเลขซ้ำกันหลายครั้ง เลือกเอาครั้งแรก
            if (len(potential_tracking) >= 12 and 
                not re.match(r'^0\d{9}$', potential_tracking) and  # ไม่ใช่เบอร์โทรศัพท์
                not potential_tracking.startswith('E_0_0_')):      # ไม่ใช่รหัสอื่น
                tracking_number = potential_tracking
                break
        if tracking_number != "Not found":
            break

    # ข้อความที่เป็นแค่ตัวอักษรล้วน ไม่ให้นับเป็นเลขติดตามพัสดุ
    if not any(c.isdigit() for c in tracking_number):
        tracking_number = "Not found"

    # ค้นหาเลขห้อง 4 ตัว
    room_match = re.search(r'ห้อง\s*(\d{4})', text)
    if room_match:
        room_number = room_match.group(1)
    else:
        room_match = re.search(r'\((\d{4})\)', text)
        if room_match:
            room_number = room_match.group(1)
        else:
            room_match = re.search(r'ชั้น\s*\d+\s*ห้อง\s*(\d{4})', text)
            if room_match:
                room_number = room_match.group(1)

    # ค้นหาชื่อผู้รับ (ปรับปรุงใหม่)
    name_patterns = [
        # ค้นหาชื่อที่อยู่หลังคำว่า "ผู้รับ"
        r'[*\s]*ผู้รับ[*\s]*\s*(?:น\.ส\.|นาย|นางสาว|นาง|คุณ|ดร\.|ผศ\.|รศ\.|ศ\.)?\s*([ก-์]+)(?:\s+[ก-์]+)*', 
        # รูปแบบเดิม
        r'\(TO\)\s*(?:น\.ส\.|นาย|นางสาว|นาง|คุณ|ดร\.|ผศ\.|รศ\.|ศ\.)?\s*([ก-์]+)(?:\s+[ก-์]+)*', 
        r'(?:ถึง|รับ)\s+(?:น\.ส\.|นาย|นางสาว|นาง|คุณ|ดร\.|ผศ\.|รศ\.|ศ\.)?\s*([ก-์]+)(?:\s+[ก-์]+)*', 
        r'(?:น\.ส\.|นาย|นางสาว|นาง|คุณ|ดร\.|ผศ\.|รศ\.|ศ\.)?\s*([ก-์]+)(?:\s+[ก-์]+)*\s*(?:\n|,|\s+)(?:หอ|บ้าน)(?:ธรรมรักษา|พัก)', 
        r'(?:น\.ส\.|นาย|นางสาว|นาง|คุณ|ดร\.|ผศ\.|รศ\.|ศ\.)\s*([ก-์]+)(?:\s+[ก-์]+)*\s*(?:\d+|หมู่|ซอย|ถนน|ถ\.|แขวง|ต\.|เขต|อ\.|จ\.)',
        r'คุณ\s+([ก-์]+)(?:\s+[ก-์]+)*',
    ]

    for pattern in name_patterns:
        match = re.search(pattern, text, re.MULTILINE)
        if match:
            full_name = match.group(1).strip()
            # ตัดคำนำหน้าออก (เพิ่มคำว่า "นางสาว" ในการตัด)
            full_name = re.sub(r'^(?:นางสาว|น\.ส\.|นาย|นาง|คุณ|ดร\.|ผศ\.|รศ\.|ศ\.)\s*', '', full_name)
            # ดึงเฉพาะชื่อจริง (คำแรก)
            first_name = full_name.split()[0]
            # ทำความสะอาดชื่อ
            first_name = re.sub(r'\s+', ' ', first_name)
            if len(first_name) >= 2 and not any(c.isdigit() for c in first_name):
                recipient_name = first_name
                break

    # ทำความสะอาดข้อมูลก่อนส่งคืน
    recipient_name = re.sub(r'\s+', ' ', recipient_name).strip()
    room_number = re.sub(r'\s+', '', room_number).strip()
    tracking_number = re.sub(r'\s+', '', tracking_number).strip()

    print(f"\nผลลัพธ์การแยกข้อมูล:")
    print(f"ชื่อผู้รับ: {recipient_name}")
    print(f"เลขห้อง: {room_number}")
    print(f"Tracking: {tracking_number}")

    return recipient_name, room_number, tracking_number

@app.route("/callback", methods=['POST'])
def callback():
    """Handle requests from LINE webhook."""
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        return "Invalid signature", 400
    return "OK", 200


def handle_image_message(event):
    """Handle image messages from LINE."""
    try:
        # Ensure the event contains an image message
        if not isinstance(event.message, ImageMessageContent):
            return

        # Get the image content
        message_content = line_bot_api.get_message_content(event.message.id)
        
        # Download and process the image
        image_content = message_content.read()

        # Process the image
        text = extract_text_from_image(image_content)
        if text:
            recipient_name, room_number, tracking_number = process_text(text)
            reply_text = (
                f"ข้อมูลที่พบ:\n"
                f"ชื่อผู้รับ: {recipient_name}\n"
                f"เลขห้อง: {room_number}\n"
                f"Tracking: {tracking_number}"
            )
        else:
            reply_text = "ไม่พบข้อความในภาพ"

        # Reply to the user
        line_bot_api.reply_message(
            ReplyMessageRequest(
                replyToken=event.reply_token,
                messages=[TextMessageContent(text=reply_text)]
            )
        )
    except Exception as e:
        line_bot_api.reply_message(
            ReplyMessageRequest(
                replyToken=event.reply_token,
                messages=[TextMessageContent(text=f"เกิดข้อผิดพลาด: {str(e)}")]
            )
        )
@handler.add(MessageEvent, message=ImageMessageContent)
def image_message_handler(event):
    handle_image_message(event)
# Register the image message handler
# @handler.add(event_type=ImageMessageContent)
# def image_message_handler(event):
#     handle_image_message(event)

# @handler.add(MessageEvent, message=ImageMessage)
# def handle_image_message(event):
#     """Handle image messages from LINE."""
#     try:
#         # Get the image content
#         message_id = event.message.id
#         message_content = line_bot_api.get_message_content(message_id)
#         image_content = b"".join(chunk for chunk in message_content)

#         # Process the image
#         text = extract_text_from_image(image_content)
#         if text:
#             recipient_name, room_number, tracking_number = process_text(text)
#             reply_text = (
#                 f"ข้อมูลที่พบ:\n"
#                 f"ชื่อผู้รับ: {recipient_name}\n"
#                 f"เลขห้อง: {room_number}\n"
#                 f"Tracking: {tracking_number}"
#             )
#         else:
#             reply_text = "ไม่พบข้อความในภาพ"

#         # Reply to the user
#         line_bot_api.reply_message(
#             event.reply_token,
#             TextMessage(text=reply_text)
#         )
#     except Exception as e:
#         line_bot_api.reply_message(
#             event.reply_token,
#             TextMessage(text=f"เกิดข้อผิดพลาด: {str(e)}")
#         )

@app.route("/callback2", methods=['POST'])
def callback2():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler_2.handle(body, signature)
    except InvalidSignatureError:
        return "Invalid signature", 400
    return "OK", 200
# @handler_2.add(MessageEvent, message=TextMessage)
# def handle_text_message_bot2(event):
#     print(f"Bot 2 received: {event}")
#     if event.message.text=="รับการแจ้งเตือน":
#         user_id = event.source.user_id
#         base_url = "https://oldk.duckdns.org/api/"  # Replace with your actual base URL
#         url = f"{base_url}?line_user_id={user_id}"

#         # Create a button template message
#         button_template = TemplateSendMessage(
#             alt_text="กรุณากรอกข้อมูลเพื่อรับการแจ้งเตือน",
#             template=ButtonsTemplate(
#                 title="กรุณากรอกข้อมูลเพื่อรับการแจ้งเตือน",
#                 text="คลิกที่ปุ่มด้านล่างเพื่อกรอกข้อมูล",
#                 actions=[
#                     URIAction(
#                         label="กรอกรหัสนักศึกษา",
#                         uri=url
#                     )
#                 ]
#             )
#         )

#         # Send the button template message
#         line_bot_api_2.reply_message(event.reply_token, button_template)
#         # reply = f"Bot 2 received: {event.message.text}"
#     # else:
#         # reply = f"Bot 2 received: {event.message.text}"
#         # line_bot_api_2.reply_message(event.reply_token, TextSendMessage(text=reply))
# @handler_2.add(PostbackEvent)
# def handle_postback_event(event):
#     # Extract data from the postback
#     postback_data = event.postback.data
#     print(f"Postback data received: {postback_data}")

#     # Example: Parse the action and tracking number
#     params = dict(item.split("=") for item in postback_data.split("&"))
#     action = params.get("action")
#     tracking_number = params.get("tracking")

#     if action == "receive":
#         connection = connect_to_database()
#         if connection:
#             cursor = connection.cursor()
#             cursor.execute(f"SELECT * FROM parcel WHERE id = '{tracking_number}'")
#             result = cursor.fetchone()
#             if result:
#                 cursor.execute(f"UPDATE parcel SET status = 'received' WHERE id = '{tracking_number}'")
#                 connection.commit()
#                 line_bot_api_2.reply_message(
#                     event.reply_token,
#                     TextSendMessage(text="ขอบคุณที่รับพัสดุ")
#                 )
#             else:
#                 line_bot_api_2.reply_message(
#                     event.reply_token,
#                     TextSendMessage(text="ไม่พบข้อมูลพัสดุ")
#                 )

#     # elif action == "reject":
#     #     line_bot_api_2.reply_message(
#     #         event.reply_token,
#     #         TextSendMessage(text="คุณปฏิเสธการรับพัสดุ")
#     #     )
@handler_2.add(MessageEvent, message=TextMessageContent)
def text_message_handler(event):
    handle_text_message_bot2(event)
def handle_text_message_bot2(event):
    print(f"Bot 2 received: {event}")
    if event.message.text=="รับการแจ้งเตือน":
        user_id = event.source.user_id
        base_url = "https://oldk.duckdns.org/api/"  # Replace with your actual base URL
        url = f"{base_url}?line_user_id={user_id}&openExternalBrowser=1"
          # Create quick reply with URI action
        quick_reply = QuickReply(
            items=[
                QuickReplyItem(
                    action=URIAction(
                        label="กรอกรหัสนักศึกษา",
                        uri=url
                    )
                )
            ]
        )

        # Send message with quick reply
        line_bot_api_2.reply_message(
            ReplyMessageRequest(
                replyToken=event.reply_token,
                messages=[
                    TextMessage(
                        text="กรุณากรอกข้อมูลเพื่อรับการแจ้งเตือน",
                        quickReply=QuickReply(
                            items=[
                                QuickReplyItem(
                                    action=URIAction(
                                        label="กรอกรหัสนักศึกษา",
                                        uri=url
                                    )
                                )
                            ]
                        )
                    )
                ]
            )
        )
    elif event.message.text=="สแกน QR Code":
        user_id = event.source.user_id
        base_url = "https://oldk.duckdns.org/api/qr_scan"  # Replace with your actual base URL
        url = f"{base_url}?line_user_id={user_id}&openExternalBrowser=1"
          # Create quick reply with URI action
        quick_reply = QuickReply(
            items=[
                QuickReplyItem(
                    action=URIAction(
                        label="กรอกรหัสนักศึกษา",
                        uri=url
                    )
                )
            ]
        )
        line_bot_api_2.reply_message(ReplyMessageRequest(
                replyToken=event.reply_token,
                messages=[
                    TextMessage(
                        text="กรุณา scan qrcode ที่พัสดุ เพื่อยืนยันการรับพัสดุ",
                        quickReply=QuickReply(
                            items=[
                                QuickReplyItem(
                                    action=URIAction(
                                        label="scan qrcode ที่พัสดุ ",
                                        uri=url
                                    )
                                )
                            ]
                        )
                    )
                ]
            )
        )

@handler_2.add(PostbackEvent)
def handle_postback_event(event):
    # Extract data from the postback
    print(f"Postback data received: {event}")
    postback_data = event.postback.data

    # Use dict comprehension for parsing
    params = dict(item.split('=', 1) for item in postback_data.split('&') if '=' in item)
    
    action = params.get("action")
    tracking_number = params.get("tracking")
    # print(f"Action: {action}, Tracking: {tracking_number}")
    print(f"reply_token : {action}")
    if action == "receive":
        connection = connect_to_database()
        if connection:
            try:
                with connection.cursor() as cursor:
                    # Use parameterized query for better security
                    cursor.execute("SELECT * FROM parcel WHERE id = %s", (tracking_number,))
                    result = cursor.fetchone()
                    if result:
                        print(f"Result: {result[3]}")
                        if result[3] == 'Confirm':
                            cursor.execute("UPDATE parcel SET status = 'received' WHERE id = %s", (tracking_number,))
                            connection.commit()
                            line_bot_api_2.reply_message(
                                ReplyMessageRequest(
                                    replyToken=event.reply_token,
                                    messages=[TextMessage(text="ขอบคุณที่รับพัสดุ")]
                                )
                            )
                        if result[3] == 'received':
                            line_bot_api_2.reply_message(
                                ReplyMessageRequest(
                                    replyToken=event.reply_token,
                                    messages=[TextMessage(text="พัสดุนี้ได้รับการยืนยันแล้ว")]
                                )
                            )
                        if result[3] == 'Pending':
                            user_id = event.source.user_id
                            base_url = "https://oldk.duckdns.org/api/qr_scan"  # Replace with your actual base URL
                            url = f"{base_url}?line_user_id={user_id}&openExternalBrowser=1"
                            line_bot_api_2.reply_message(ReplyMessageRequest(
                                    replyToken=event.reply_token,
                                    messages=[
                                        TextMessage(
                                            text="กรุณา scan qrcode ที่พัสดุ เพื่อยืนยันการรับพัสดุ",
                                            quickReply=QuickReply(
                                                items=[
                                                    QuickReplyItem(
                                                        action=URIAction(
                                                            label="scan qrcode ที่พัสดุ ",
                                                            uri=url
                                                        )
                                                    )
                                                ]
                                            )
                                        )
                                    ]
                                )
                            )
                            # line_bot_api_2.reply_message(
                            #     ReplyMessageRequest(
                            #         replyToken=event.reply_token,
                            #         messages=[TextMessage(text="กรุณา scan qrcode ที่พัสดุ เพื่อยืนยันการรับพัสดุ")]
                            #     )
                            # )
                    else:
                        line_bot_api_2.reply_message(
                            ReplyMessageRequest(
                                replyToken=event.reply_token,
                                messages=[TextMessage(text="ไม่พบข้อมูลพัสดุ")]
                            )
                        )
            except Exception as e:
                print(f"Database error: {e}")
                line_bot_api_2.reply_message(
                    ReplyMessageRequest(
                        replyToken=event.reply_token,
                        messages=[TextMessageContent(text="เกิดข้อผิดพลาดในการดำเนินการ")]
                    )
                )
            finally:
                # Ensure connection is closed
                if connection:
                    connection.close()
    elif action == "reject":
        connection = connect_to_database()
        if connection:
            try:
                with connection.cursor() as cursor:
                    # Use parameterized query for better security
                    cursor.execute("SELECT * FROM parcel WHERE id = %s", (tracking_number,))
                    result = cursor.fetchone()
                    if result:
                        cursor.execute("UPDATE parcel SET status = 'Deny' WHERE id = %s", (tracking_number,))
                        connection.commit()
                        line_bot_api_2.reply_message(
                                ReplyMessageRequest(
                                    replyToken=event.reply_token,
                                    messages=[TextMessage(text="ยกเลิกสำเร็จแล้ว")]
                                )
                            )
                    else:
                        line_bot_api_2.reply_message(
                            ReplyMessageRequest(
                                replyToken=event.reply_token,
                                messages=[TextMessage(text="ไม่พบข้อมูลพัสดุ")]
                            )
                        )
            except Exception as e:
                print(f"Database error: {e}")
                line_bot_api_2.reply_message(
                    ReplyMessageRequest(
                        replyToken=event.reply_token,
                        messages=[TextMessageContent(text="เกิดข้อผิดพลาดในการดำเนินการ")]
                    )
                )
            finally:
                # Ensure connection is closed
                if connection:
                    connection.close()

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, debug=True)
    
