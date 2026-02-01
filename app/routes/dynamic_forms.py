from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from app.db import get_conn
from app.config import settings
import json
import hashlib
from datetime import date, time, datetime

router = APIRouter()

# ============ Models ============

class FormFieldOption(BaseModel):
    value: str
    label: str
    capacity: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = None

class FormFieldCreate(BaseModel):
    field_name: str
    field_label: str
    field_type: str  # text, email, phone, select, multiselect, date, time, textarea, checkbox, radio
    field_order: int = 0
    is_required: bool = False
    placeholder: Optional[str] = None
    help_text: Optional[str] = None
    validation_rules: Optional[Dict[str, Any]] = None
    options: Optional[List[FormFieldOption]] = None
    default_value: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

class FormFieldUpdate(BaseModel):
    field_label: Optional[str] = None
    field_type: Optional[str] = None
    field_order: Optional[int] = None
    is_required: Optional[bool] = None
    placeholder: Optional[str] = None
    help_text: Optional[str] = None
    validation_rules: Optional[Dict[str, Any]] = None
    options: Optional[List[FormFieldOption]] = None
    default_value: Optional[str] = None
    is_active: Optional[bool] = None
    metadata: Optional[Dict[str, Any]] = None

class FormConfigurationCreate(BaseModel):
    org_id: str
    bot_id: str
    name: str
    description: Optional[str] = None
    industry: Optional[str] = None

class FormConfigurationUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    industry: Optional[str] = None
    is_active: Optional[bool] = None

class BookingResourceCreate(BaseModel):
    org_id: str
    bot_id: str
    resource_type: str  # doctor, room, equipment, staff, service
    resource_name: str
    resource_code: Optional[str] = None
    description: Optional[str] = None
    capacity_per_slot: int = 1
    metadata: Optional[Dict[str, Any]] = None

class BookingResourceUpdate(BaseModel):
    resource_name: Optional[str] = None
    resource_code: Optional[str] = None
    description: Optional[str] = None
    capacity_per_slot: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None

class ResourceScheduleCreate(BaseModel):
    resource_id: str
    day_of_week: Optional[int] = None  # 0-6 for recurring, null for specific date
    specific_date: Optional[date] = None
    start_time: time
    end_time: time
    slot_duration_minutes: int = 30
    is_available: bool = True
    metadata: Optional[Dict[str, Any]] = None

class BookingCreate(BaseModel):
    org_id: str
    bot_id: str
    customer_name: str
    customer_email: str
    customer_phone: Optional[str] = None
    booking_date: date
    start_time: time
    end_time: time
    resource_id: Optional[str] = None
    form_data: Dict[str, Any]
    notes: Optional[str] = None

# ============ Form Configuration Endpoints ============

@router.post("/form-configs")
def create_form_configuration(config: FormConfigurationCreate):
    """Create a new form configuration for a bot"""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                insert into form_configurations (org_id, bot_id, name, description, industry)
                values (%s, %s, %s, %s, %s)
                returning id, created_at
            """, (config.org_id, config.bot_id, config.name, config.description, config.industry))
            result = cur.fetchone()
            conn.commit()
            return {
                "id": str(result[0]),
                "created_at": result[1].isoformat(),
                **config.model_dump()
            }
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()

@router.get("/form-configs/{bot_id}")
def get_form_configuration(bot_id: str):
    """Get form configuration for a bot"""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                select id, org_id, bot_id, name, description, industry, is_active, created_at, updated_at
                from form_configurations
                where bot_id = %s
            """, (bot_id,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Form configuration not found")
            
            return {
                "id": str(row[0]),
                "org_id": str(row[1]),
                "bot_id": str(row[2]),
                "name": row[3],
                "description": row[4],
                "industry": row[5],
                "is_active": row[6],
                "created_at": row[7].isoformat(),
                "updated_at": row[8].isoformat()
            }
    finally:
        conn.close()

@router.put("/form-configs/{config_id}")
def update_form_configuration(config_id: str, update: FormConfigurationUpdate):
    """Update form configuration"""
    conn = get_conn()
    try:
        fields = []
        values = []
        for key, value in update.model_dump(exclude_unset=True).items():
            fields.append(f"{key} = %s")
            values.append(value)
        
        if not fields:
            raise HTTPException(status_code=400, detail="No fields to update")
        
        values.append(config_id)
        
        with conn.cursor() as cur:
            cur.execute(f"""
                update form_configurations
                set {', '.join(fields)}, updated_at = now()
                where id = %s
                returning id
            """, values)
            result = cur.fetchone()
            if not result:
                raise HTTPException(status_code=404, detail="Form configuration not found")
            conn.commit()
            return {"success": True, "id": str(result[0])}
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()

# ============ Form Fields Endpoints ============

@router.post("/form-configs/{config_id}/fields")
def create_form_field(config_id: str, field: FormFieldCreate):
    """Add a field to a form configuration"""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            # Convert to dict first, then handle options
            field_dict = field.model_dump()
            options_json = json.dumps(field_dict['options']) if field_dict.get('options') else None
            validation_json = json.dumps(field_dict['validation_rules']) if field_dict.get('validation_rules') else None
            metadata_json = json.dumps(field_dict['metadata']) if field_dict.get('metadata') else None
            
            cur.execute("""
                insert into form_fields 
                (form_config_id, field_name, field_label, field_type, field_order, is_required,
                 placeholder, help_text, validation_rules, options, default_value, metadata)
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                returning id, created_at
            """, (config_id, field.field_name, field.field_label, field.field_type, field.field_order,
                  field.is_required, field.placeholder, field.help_text, validation_json, options_json,
                  field.default_value, metadata_json))
            result = cur.fetchone()
            conn.commit()
            return {
                "id": str(result[0]),
                "created_at": result[1].isoformat(),
                **field_dict
            }
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()

@router.get("/form-configs/{config_id}/fields")
def get_form_fields(config_id: str, include_inactive: bool = False):
    """Get all fields for a form configuration"""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            where_clause = "where form_config_id = %s"
            if not include_inactive:
                where_clause += " and is_active = true"
            
            cur.execute(f"""
                select id, field_name, field_label, field_type, field_order, is_required,
                       placeholder, help_text, validation_rules, options, default_value, is_active, metadata
                from form_fields
                {where_clause}
                order by field_order
            """, (config_id,))
            
            fields = []
            for row in cur.fetchall():
                fields.append({
                    "id": str(row[0]),
                    "field_name": row[1],
                    "field_label": row[2],
                    "field_type": row[3],
                    "field_order": row[4],
                    "is_required": row[5],
                    "placeholder": row[6],
                    "help_text": row[7],
                    "validation_rules": row[8],
                    "options": row[9],
                    "default_value": row[10],
                    "is_active": row[11],
                    "metadata": row[12]
                })
            return {"fields": fields}
    finally:
        conn.close()

@router.put("/form-fields/{field_id}")
def update_form_field(field_id: str, update: FormFieldUpdate):
    """Update a form field"""
    conn = get_conn()
    try:
        fields = []
        values = []
        
        for key, value in update.model_dump(exclude_unset=True).items():
            if key == 'options' and value is not None:
                fields.append(f"{key} = %s")
                # value is already a list of dicts after model_dump()
                values.append(json.dumps(value))
            elif key == 'validation_rules' and value is not None:
                fields.append(f"{key} = %s")
                values.append(json.dumps(value))
            elif key == 'metadata' and value is not None:
                fields.append(f"{key} = %s")
                values.append(json.dumps(value))
            else:
                fields.append(f"{key} = %s")
                values.append(value)
        
        if not fields:
            raise HTTPException(status_code=400, detail="No fields to update")
        
        values.append(field_id)
        
        with conn.cursor() as cur:
            cur.execute(f"""
                update form_fields
                set {', '.join(fields)}, updated_at = now()
                where id = %s
                returning id
            """, values)
            result = cur.fetchone()
            if not result:
                raise HTTPException(status_code=404, detail="Field not found")
            conn.commit()
            return {"success": True, "id": str(result[0])}
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()

@router.delete("/form-fields/{field_id}")
def delete_form_field(field_id: str, hard_delete: bool = False):
    """Delete a form field (soft delete by default)"""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            if hard_delete:
                cur.execute("delete from form_fields where id = %s returning id", (field_id,))
            else:
                cur.execute("""
                    update form_fields set is_active = false, updated_at = now()
                    where id = %s returning id
                """, (field_id,))
            
            result = cur.fetchone()
            if not result:
                raise HTTPException(status_code=404, detail="Field not found")
            conn.commit()
            return {"success": True, "id": str(result[0])}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()

# ============ Resources Endpoints ============

@router.post("/resources")
def create_resource(resource: BookingResourceCreate):
    """Create a bookable resource (doctor, room, etc.)"""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            metadata_json = json.dumps(resource.metadata) if resource.metadata else None
            
            cur.execute("""
                insert into booking_resources 
                (org_id, bot_id, resource_type, resource_name, resource_code, description, capacity_per_slot, metadata)
                values (%s, %s, %s, %s, %s, %s, %s, %s)
                returning id, created_at
            """, (resource.org_id, resource.bot_id, resource.resource_type, resource.resource_name,
                  resource.resource_code, resource.description, resource.capacity_per_slot, metadata_json))
            result = cur.fetchone()
            conn.commit()
            return {
                "id": str(result[0]),
                "created_at": result[1].isoformat(),
                **resource.model_dump()
            }
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()

@router.get("/resources/{bot_id}")
def get_resources(bot_id: str, resource_type: Optional[str] = None, active_only: bool = True):
    """Get all resources for a bot"""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            where_clauses = ["bot_id = %s"]
            params = [bot_id]
            
            if resource_type:
                where_clauses.append("resource_type = %s")
                params.append(resource_type)
            
            if active_only:
                where_clauses.append("is_active = true")
            
            cur.execute(f"""
                select id, org_id, bot_id, resource_type, resource_name, resource_code,
                       department, description, capacity_per_slot, metadata, is_active, created_at
                from booking_resources
                where {' and '.join(where_clauses)}
                order by resource_name
            """, params)
            
            resources = []
            for row in cur.fetchall():
                resources.append({
                    "id": str(row[0]),
                    "org_id": str(row[1]),
                    "bot_id": str(row[2]),
                    "resource_type": row[3],
                    "resource_name": row[4],
                    "resource_code": row[5],
                    "department": row[6],
                    "description": row[7],
                    "capacity_per_slot": row[8],
                    "metadata": row[9],
                    "is_active": row[10],
                    "created_at": row[11].isoformat()
                })
            return {"resources": resources}
    finally:
        conn.close()

@router.put("/resources/{resource_id}")
def update_resource(resource_id: str, update: BookingResourceUpdate):
    """Update a resource"""
    conn = get_conn()
    try:
        fields = []
        values = []
        
        for key, value in update.model_dump(exclude_unset=True).items():
            if key == 'metadata' and value is not None:
                fields.append(f"{key} = %s")
                values.append(json.dumps(value))
            else:
                fields.append(f"{key} = %s")
                values.append(value)
        
        if not fields:
            raise HTTPException(status_code=400, detail="No fields to update")
        
        values.append(resource_id)
        
        with conn.cursor() as cur:
            cur.execute(f"""
                update booking_resources
                set {', '.join(fields)}, updated_at = now()
                where id = %s
                returning id
            """, values)
            result = cur.fetchone()
            if not result:
                raise HTTPException(status_code=404, detail="Resource not found")
            conn.commit()
            return {"success": True, "id": str(result[0])}
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()
 
@router.delete("/resources/{resource_id}")
def delete_resource(resource_id: str, hard_delete: bool = False):
    """Delete a resource. Soft delete by default (sets is_active=false)."""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            # Remove schedules for the resource
            cur.execute("delete from resource_schedules where resource_id = %s", (resource_id,))
            if hard_delete:
                cur.execute("delete from booking_resources where id = %s returning id", (resource_id,))
            else:
                cur.execute("""
                    update booking_resources
                    set is_active = false, updated_at = now()
                    where id = %s
                    returning id
                """, (resource_id,))
            result = cur.fetchone()
            if not result:
                raise HTTPException(status_code=404, detail="Resource not found")
            conn.commit()
            return {"success": True, "id": str(result[0])}
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()

# ============ Resource Schedules Endpoints ============

@router.post("/resources/{resource_id}/schedules")
def create_resource_schedule(resource_id: str, schedule: ResourceScheduleCreate):
    """Create availability schedule for a resource"""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            # Check for duplicates
            if schedule.day_of_week is not None:
                # Check for duplicate weekly slot (same day_of_week and overlapping times)
                cur.execute("""
                    select id from resource_schedules
                    where resource_id = %s 
                    and day_of_week = %s
                    and specific_date is null
                    and start_time = %s
                """, (resource_id, schedule.day_of_week, schedule.start_time))
                if cur.fetchone():
                    raise HTTPException(status_code=409, detail=f"A schedule for this day and time already exists")
            else:
                # Check for duplicate specific date slot (same date and overlapping times)
                cur.execute("""
                    select id from resource_schedules
                    where resource_id = %s 
                    and specific_date = %s
                    and start_time = %s
                """, (resource_id, schedule.specific_date, schedule.start_time))
                if cur.fetchone():
                    raise HTTPException(status_code=409, detail=f"A schedule for this date and time already exists")
            
            metadata_json = json.dumps(schedule.metadata) if schedule.metadata else None
            
            cur.execute("""
                insert into resource_schedules 
                (resource_id, day_of_week, specific_date, start_time, end_time, slot_duration_minutes, is_available, metadata)
                values (%s, %s, %s, %s, %s, %s, %s, %s)
                returning id, created_at
            """, (resource_id, schedule.day_of_week, schedule.specific_date, schedule.start_time,
                  schedule.end_time, schedule.slot_duration_minutes, schedule.is_available, metadata_json))
            result = cur.fetchone()
            conn.commit()
            return {
                "id": str(result[0]),
                "resource_id": resource_id,
                "created_at": result[1].isoformat(),
                **schedule.model_dump()
            }
    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()

@router.get("/resources/{resource_id}/schedules")
def list_resource_schedules(resource_id: str):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                select id, day_of_week, specific_date, start_time, end_time, slot_duration_minutes, is_available, metadata, created_at
                from resource_schedules
                where resource_id = %s
                order by specific_date nulls last, day_of_week, start_time
            """, (resource_id,))
            items = []
            for row in cur.fetchall():
                items.append({
                    "id": str(row[0]),
                    "day_of_week": row[1],
                    "specific_date": row[2].isoformat() if row[2] else None,
                    "start_time": str(row[3]),
                    "end_time": str(row[4]),
                    "slot_duration_minutes": row[5],
                    "is_available": row[6],
                    "metadata": row[7],
                    "created_at": row[8].isoformat() if row[8] else None
                })
            return {"schedules": items}
    finally:
        conn.close()

@router.delete("/schedules/{schedule_id}")
def delete_schedule(schedule_id: str):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("delete from resource_schedules where id = %s returning id", (schedule_id,))
            result = cur.fetchone()
            if not result:
                raise HTTPException(status_code=404, detail="Schedule not found")
            conn.commit()
            return {"success": True, "id": str(result[0])}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()

@router.get("/resources/{resource_id}/available-slots")
def get_available_slots(resource_id: str, booking_date: date):
    """Get available time slots for a resource on a specific date"""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            # Get bot_id and bot booking settings for this resource
            cur.execute("""
                select bot_id from booking_resources where id = %s
            """, (resource_id,))
            resource_row = cur.fetchone()
            if not resource_row:
                raise HTTPException(status_code=404, detail="Resource not found")
            
            bot_id = resource_row[0]
            
            # Get bot booking settings for min_notice and max_future
            cur.execute("""
                select timezone, min_notice_minutes, max_future_days
                from bot_booking_settings
                where bot_id = %s
            """, (bot_id,))
            
            settings_row = cur.fetchone()
            if settings_row:
                timezone = settings_row[0]
                min_notice = settings_row[1] or 60
                max_future = settings_row[2] or 60
            else:
                timezone = None
                min_notice = 60
                max_future = 60
            
            # Get all slots from database function
            cur.execute("""
                select slot_start, slot_end, available_capacity
                from get_available_slots(%s, %s)
            """, (resource_id, booking_date))
            
            # Filter slots based on min_notice and max_future
            import datetime
            import zoneinfo
            
            now = datetime.datetime.now(datetime.timezone.utc)
            if min_notice:
                earliest_allowed = now + datetime.timedelta(minutes=min_notice)
            else:
                earliest_allowed = now
            
            if max_future:
                latest_allowed = now + datetime.timedelta(days=max_future)
            else:
                latest_allowed = None
            
            slots = []
            for row in cur.fetchall():
                slot_start_time = row[0]
                slot_end_time = row[1]
                available_capacity = row[2]
                
                # Create datetime for this slot
                slot_datetime = datetime.datetime.combine(booking_date, slot_start_time)
                
                # Apply timezone if configured
                if timezone:
                    try:
                        tz = zoneinfo.ZoneInfo(timezone)
                        slot_datetime = slot_datetime.replace(tzinfo=tz)
                    except:
                        # If timezone fails, assume UTC
                        slot_datetime = slot_datetime.replace(tzinfo=datetime.timezone.utc)
                else:
                    slot_datetime = slot_datetime.replace(tzinfo=datetime.timezone.utc)
                
                # Check if slot meets min_notice and max_future constraints
                if slot_datetime >= earliest_allowed:
                    if latest_allowed is None or slot_datetime <= latest_allowed:
                        slots.append({
                            "start_time": str(slot_start_time),
                            "end_time": str(slot_end_time),
                            "available_capacity": available_capacity
                        })
            
            return {"date": str(booking_date), "slots": slots}
    finally:
        conn.close()

@router.get("/bots/{bot_id}/available-slots")
def get_bot_available_slots(bot_id: str, booking_date: date):
    """Get available time slots for a bot on a specific date (bot-level capacity check).
    
    NOTE: This endpoint is DISABLED if the bot has active resources configured.
    If resources are configured, use /resources/{resource_id}/available-slots instead.
    """
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            # CHECK: If bot has resources configured, reject global slot query
            cur.execute("""
                SELECT COUNT(*) FROM booking_resources 
                WHERE bot_id = %s AND is_active = true
            """, (bot_id,))
            has_resources = cur.fetchone()[0] > 0
            
            if has_resources:
                # Get list of available resources for user convenience
                cur.execute("""
                    SELECT id, resource_name FROM booking_resources 
                    WHERE bot_id = %s AND is_active = true
                    ORDER BY resource_name
                """, (bot_id,))
                resources = [{"id": row[0], "name": row[1]} for row in cur.fetchall()]
                
                raise HTTPException(
                    status_code=400,
                    detail={
                        "message": "This bot uses specific resources. Please select a resource first.",
                        "available_resources": resources
                    }
                )
            
            # Get bot booking settings
            cur.execute("""
                select timezone, slot_duration_minutes, capacity_per_slot, 
                       available_windows, min_notice_minutes, max_future_days
                from bot_booking_settings
                where bot_id = %s
            """, (bot_id,))
            
            settings_row = cur.fetchone()
            if not settings_row:
                # Return default settings if not configured
                slot_duration = 30
                capacity = 1
                available_windows = None
                timezone = None
                min_notice = 60
                max_future = 60
            else:
                timezone = settings_row[0]
                slot_duration = settings_row[1] or 30
                capacity = settings_row[2] or 1
                available_windows = settings_row[3]
                min_notice = settings_row[4] or 60
                max_future = settings_row[5] or 60
            
            # Generate time slots for the day
            import datetime
            import zoneinfo
            
            # Convert date to datetime range
            if timezone:
                try:
                    tz = zoneinfo.ZoneInfo(timezone)
                    start_of_day = datetime.datetime.combine(booking_date, datetime.time.min, tzinfo=tz)
                    end_of_day = datetime.datetime.combine(booking_date, datetime.time.max, tzinfo=tz)
                except:
                    start_of_day = datetime.datetime.combine(booking_date, datetime.time.min)
                    end_of_day = datetime.datetime.combine(booking_date, datetime.time.max)
            else:
                start_of_day = datetime.datetime.combine(booking_date, datetime.time.min)
                end_of_day = datetime.datetime.combine(booking_date, datetime.time.max)
            
            # Check min notice and max future constraints
            now = datetime.datetime.now(datetime.timezone.utc)
            if min_notice:
                earliest_allowed = now + datetime.timedelta(minutes=min_notice)
            else:
                earliest_allowed = now
            
            if max_future:
                latest_allowed = now + datetime.timedelta(days=max_future)
            else:
                latest_allowed = None
            
            # Get business hours for the day
            def is_in_business_hours(time_obj: datetime.time) -> bool:
                if not available_windows:
                    return True
                
                day_name = ["mon","tue","wed","thu","fri","sat","sun"][booking_date.weekday()]
                minutes_of_day = time_obj.hour * 60 + time_obj.minute
                
                for window in available_windows:
                    if window.get("day", "").lower()[:3] == day_name:
                        try:
                            start_parts = window.get("start", "09:00").split(":")
                            end_parts = window.get("end", "17:00").split(":")
                            start_minutes = int(start_parts[0]) * 60 + int(start_parts[1])
                            end_minutes = int(end_parts[0]) * 60 + int(end_parts[1])
                            
                            if start_minutes <= minutes_of_day < end_minutes:
                                return True
                        except:
                            continue
                return False
            
            # Generate all possible slots for the day
            current_time = datetime.time(0, 0)
            all_slots = []
            
            while current_time < datetime.time(23, 59):
                if is_in_business_hours(current_time):
                    # Calculate end time
                    total_minutes = current_time.hour * 60 + current_time.minute + slot_duration
                    end_hour = total_minutes // 60
                    end_minute = total_minutes % 60
                    
                    if end_hour < 24:
                        end_time = datetime.time(end_hour, end_minute)
                        
                        # Check if slot is within allowed time range
                        slot_datetime = datetime.datetime.combine(booking_date, current_time)
                        if timezone:
                            try:
                                slot_datetime = slot_datetime.replace(tzinfo=zoneinfo.ZoneInfo(timezone))
                            except:
                                pass
                        
                        # Check constraints
                        if slot_datetime >= earliest_allowed:
                            if latest_allowed is None or slot_datetime <= latest_allowed:
                                all_slots.append({
                                    "start_time": current_time,
                                    "end_time": end_time
                                })
                
                # Move to next slot
                total_minutes = current_time.hour * 60 + current_time.minute + slot_duration
                if total_minutes >= 24 * 60:
                    break
                current_time = datetime.time(total_minutes // 60, total_minutes % 60)
            
            # Check capacity for each slot
            available_slots = []
            for slot in all_slots:
                cur.execute("""
                    select count(*) 
                    from bookings
                    where bot_id = %s
                      and booking_date = %s
                      and status not in ('cancelled', 'rejected')
                      and (
                        (start_time <= %s and end_time > %s) or
                        (start_time < %s and end_time >= %s) or
                        (start_time >= %s and end_time <= %s)
                      )
                """, (bot_id, booking_date, slot["start_time"], slot["start_time"], slot["end_time"], slot["end_time"], slot["start_time"], slot["end_time"]), prepare=False)
                
                booked_count = cur.fetchone()[0]
                available_capacity = capacity - booked_count
                
                if available_capacity > 0:
                    available_slots.append({
                        "start_time": str(slot["start_time"]),
                        "end_time": str(slot["end_time"]),
                        "available_capacity": available_capacity
                    })
            
            return {"date": str(booking_date), "slots": available_slots}
    finally:
        conn.close()

# ============ Bookings Endpoints ============

@router.post("/bookings")
def create_booking(booking: BookingCreate):
    """Create a new booking with dynamic form data and sync to Google Calendar"""
    conn = get_conn()
    external_event_id = None
    calendar_service = None  # Store service for later update
    calendar_id = None  # Store calendar ID for later update
    
    try:
        with conn.cursor() as cur:
            # CHECK: If bot has active resources, require resource-specific booking
            cur.execute("""
                SELECT COUNT(*) FROM booking_resources 
                WHERE bot_id = %s AND is_active = true
            """, (booking.bot_id,))
            has_resources = cur.fetchone()[0] > 0
            
            # Reject global bookings if resources are configured
            if not booking.resource_id and has_resources:
                raise HTTPException(
                    status_code=400, 
                    detail="Resources are configured for this bot. Please select a specific resource (doctor, room, etc.) to complete your booking."
                )
            
            # Check capacity if resource specified
            if booking.resource_id:
                cur.execute("""
                    select check_resource_capacity(%s, %s, %s, %s)
                """, (booking.resource_id, booking.booking_date, booking.start_time, booking.end_time))
                has_capacity = cur.fetchone()[0]
                if not has_capacity:
                    raise HTTPException(status_code=409, detail="No capacity available for this resource at this time. Please choose another time.")
                
                # Get resource name
                cur.execute("select resource_name from booking_resources where id = %s", (booking.resource_id,))
                resource_name = cur.fetchone()[0]
            else:
                resource_name = None
                # Check bot-level slot capacity when no resource specified (only if NO resources)
                cur.execute("""
                    select check_slot_capacity(%s, %s, %s, %s)
                """, (booking.bot_id, booking.booking_date, booking.start_time, booking.end_time))
                has_capacity = cur.fetchone()[0]
                if not has_capacity:
                    raise HTTPException(status_code=409, detail="No capacity available for this time slot. Please choose another time.")
            
            # Check for duplicate booking for the same customer
            cur.execute("""
                select id from bookings 
                where bot_id = %s and customer_email = %s and booking_date = %s and start_time = %s and status = 'confirmed'
            """, (booking.bot_id, booking.customer_email, booking.booking_date, booking.start_time))
            if cur.fetchone():
                print(f"⚠ Duplicate booking attempt: {booking.customer_email} at {booking.booking_date} {booking.start_time}")
                raise HTTPException(status_code=409, detail="You already have a booking for this time slot.")

            # Get form config ID
            cur.execute("""
                select id from form_configurations where bot_id = %s
            """, (booking.bot_id,))
            form_config_result = cur.fetchone()
            form_config_id = form_config_result[0] if form_config_result else None
            
            # Try to sync with Google Calendar
            try:
                # Check if calendar is connected
                cur.execute("""
                    select calendar_id, access_token_enc, refresh_token_enc 
                    from bot_calendar_oauth 
                    where bot_id = %s and provider = 'google'
                """, (booking.bot_id,))
                cal_row = cur.fetchone()
                
                if not cal_row:
                    print(f"⚠ No Google Calendar connected for bot {booking.bot_id}")
                else:
                    cal_id, at_enc, rt_enc = cal_row
                    calendar_id = cal_id  # Store for later use
                    print(f"📅 Calendar found: {cal_id or 'primary'}")
                    
                    # Import calendar functions
                    from app.services.calendar_google import _decrypt, _encrypt, build_service_from_tokens, create_event_oauth, refresh_access_token
                    
                    # Decrypt tokens
                    at = _decrypt(at_enc) if at_enc else None
                    rt = _decrypt(rt_enc) if rt_enc else None
                    
                    print(f"🔑 Tokens decrypted - AT: {'✓' if at else '✗'}, RT: {'✓' if rt else '✗'}")
                    
                    # Try to refresh token if we have a refresh token
                    if rt and not at:
                        print("🔄 Access token missing, attempting refresh...")
                        new_at = refresh_access_token(rt)
                        if new_at:
                            at = new_at
                            # Save the new access token
                            at_enc_new = _encrypt(new_at)
                            cur.execute("""
                                update bot_calendar_oauth 
                                set access_token_enc = %s, updated_at = now()
                                where bot_id = %s and provider = 'google'
                            """, (at_enc_new, booking.bot_id))
                            conn.commit()
                            print("✓ Access token refreshed and saved")
                    
                    # Build service
                    svc = build_service_from_tokens(at or "", rt, None)
                    
                    if not svc:
                        print("✗ Failed to build Google Calendar service")
                        print("   Please reconnect your Google Calendar in bot settings")
                    else:
                        print("✓ Google Calendar service built successfully")
                        calendar_service = svc  # Store for later update
                    
                    if svc:
                        # Get timezone from calendar config or booking settings
                        timezone = None
                        try:
                            # First try to get from calendar OAuth config
                            cur.execute("""
                                select timezone from bot_calendar_oauth
                                where bot_id = %s and provider = 'google'
                            """, (booking.bot_id,))
                            tz_row = cur.fetchone()
                            if tz_row and tz_row[0]:
                                timezone = tz_row[0]
                            
                            # If not found, try booking settings
                            if not timezone:
                                cur.execute("""
                                    select timezone from bot_booking_settings
                                    where bot_id = %s
                                """, (booking.bot_id,))
                                bs_row = cur.fetchone()
                                if bs_row and bs_row[0]:
                                    timezone = bs_row[0]
                        except Exception as e:
                            print(f"⚠️ Error fetching timezone: {str(e)}")
                        
                        # Default to UTC if no timezone configured
                        if not timezone:
                            timezone = "UTC"
                        
                        print(f"🌍 Using timezone: {timezone}")
                        print(f"📋 Form data: {booking.form_data}")
                        
                        # Create ISO datetime strings with timezone
                        start_iso = f"{booking.booking_date}T{booking.start_time}"
                        end_iso = f"{booking.booking_date}T{booking.end_time}"
                        
                        print(f"📅 Creating event: {start_iso} to {end_iso} ({timezone})")
                        
                        # Create event summary
                        summary = f"Appointment: {booking.customer_name}"
                        if resource_name:
                            summary += f" with {resource_name}"
                        
                        print(f"📋 Event summary: {summary}")
                        
                        # Build detailed description with all form data (email-friendly)
                        description_parts = [
                            "Appointment Details",
                            "",
                            "Appointment ID: PENDING (will be updated)",
                            f"Customer: {booking.customer_name}",
                            f"Email: {booking.customer_email}",
                        ]
                        
                        if booking.customer_phone:
                            description_parts.append(f"Phone: {booking.customer_phone}")
                        
                        if resource_name:
                            description_parts.append(f"Resource/Staff: {resource_name}")
                        
                        # Get field labels from form configuration for better display
                        field_labels = {}
                        try:
                            cur.execute("""
                                select field_name, field_label, field_type
                                from form_fields
                                where form_config_id = %s and is_active = true
                            """, (form_config_id,))
                            for field_row in cur.fetchall():
                                field_labels[field_row[0]] = {
                                    'label': field_row[1],
                                    'type': field_row[2]
                                }
                        except Exception:
                            pass
                        
                        # Add all custom form fields with proper labels
                        if booking.form_data:
                            print(f"📝 Processing {len(booking.form_data)} form fields...")
                            description_parts.append("")
                            description_parts.append("Form Details")
                            description_parts.append("")
                            
                            for field_name, field_value in booking.form_data.items():
                                print(f"   Field: {field_name} = {field_value}")
                                if field_value is not None and field_value != '':
                                    # Use actual field label if available, otherwise format field name
                                    if field_name in field_labels:
                                        label = field_labels[field_name]['label']
                                    else:
                                        label = field_name.replace('_', ' ').title()
                                    
                                    # Format value based on type
                                    if isinstance(field_value, bool):
                                        display_value = '✓ Yes' if field_value else '✗ No'
                                    elif isinstance(field_value, list):
                                        display_value = ', '.join(str(v) for v in field_value)
                                    else:
                                        display_value = str(field_value)
                                    
                                    description_parts.append(f"- {label}: {display_value}")
                                    print(f"   Added to description: {label} = {display_value}")
                        else:
                            print("⚠ No form data provided in booking")
                        
                        if booking.notes:
                            description_parts.append("")
                            description_parts.append("Additional Notes")
                            description_parts.append(f"{booking.notes}")
                        
                        description_parts.append("")
                        description_parts.append(f"Created: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                        
                        event_description = "\n".join(description_parts)
                        
                        # Create event in Google Calendar with full details
                        attendees = [booking.customer_email] if booking.customer_email else None
                        
                        # Generate a deterministic event ID to prevent duplicates
                        # Google Calendar IDs must be 0-9, a-v. Hex (0-9, a-f) is safe.
                        unique_string = f"{booking.bot_id}_{booking.customer_email}_{booking.booking_date}_{booking.start_time}"
                        custom_event_id = hashlib.md5(unique_string.encode()).hexdigest()
                        
                        print(f"🔄 Calling create_event_oauth...")
                        print(f"   Calendar ID: {cal_id or 'primary'}")
                        print(f"   Summary: {summary}")
                        print(f"   Start: {start_iso}")
                        print(f"   End: {end_iso}")
                        print(f"   Timezone: {timezone}")
                        print(f"   Attendees: {attendees}")
                        print(f"   Custom Event ID: {custom_event_id}")
                        print(f"   Description length: {len(event_description)} chars")
                        
                        external_event_id = create_event_oauth(
                            svc, 
                            cal_id or "primary", 
                            summary, 
                            start_iso, 
                            end_iso, 
                            attendees,
                            timezone,  # timezone
                            event_description,  # description with all form details
                            custom_event_id  # Pass our deterministic ID
                        )
                        
                        # If failed due to expired token, try refreshing and retry once
                        if not external_event_id and rt:
                            print("⚠ Event creation failed, attempting token refresh...")
                            new_at = refresh_access_token(rt)
                            if new_at:
                                print("✓ Token refreshed, retrying event creation...")
                                # Update token in database
                                at_enc_new = _encrypt(new_at)
                                cur.execute("""
                                    update bot_calendar_oauth 
                                    set access_token_enc = %s, updated_at = now()
                                    where bot_id = %s and provider = 'google'
                                """, (at_enc_new, booking.bot_id))
                                conn.commit()
                                
                                # Rebuild service with new token
                                svc = build_service_from_tokens(new_at, rt, None)
                                if svc:
                                    external_event_id = create_event_oauth(
                                        svc, 
                                        cal_id or "primary", 
                                        summary, 
                                        start_iso, 
                                        end_iso, 
                                        attendees,
                                        timezone,
                                        event_description,
                                        custom_event_id  # Pass our deterministic ID on retry too
                                    )
                        
                        if external_event_id:
                            print(f"✓ Calendar event created successfully: {external_event_id}")
                        else:
                            print("✗ Failed to create calendar event (returned None)")
                            print("   This usually means:")
                            print("   1. Token expired/invalid")
                            print("   2. Calendar API error")
                            print("   3. Insufficient permissions")
                            print("✗ Failed to create calendar event (returned None)")
            except Exception as calendar_error:
                # Log calendar error but don't fail the booking
                print(f"✗ Calendar sync failed: {calendar_error}")
                import traceback
                traceback.print_exc()
            
            form_data_json = json.dumps(booking.form_data)
            
            cur.execute("""
                insert into bookings 
                (org_id, bot_id, form_config_id, customer_name, customer_email, customer_phone,
                 booking_date, start_time, end_time, resource_id, resource_name, form_data, notes, 
                 status, calendar_event_id)
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'confirmed', %s)
                returning id, created_at
            """, (booking.org_id, booking.bot_id, form_config_id, booking.customer_name,
                  booking.customer_email, booking.customer_phone, booking.booking_date,
                  booking.start_time, booking.end_time, booking.resource_id, resource_name,
                  form_data_json, booking.notes, external_event_id))
            result = cur.fetchone()
            booking_id = result[0]
            conn.commit()
            
            print(f"✓ Booking created successfully - ID: {booking_id}, Calendar Event: {external_event_id or 'Not synced'}")
            
            # Update calendar event with actual appointment ID
            if external_event_id and calendar_service:
                try:
                    print(f"🔄 Updating calendar event with Appointment ID: {booking_id}")
                    
                    # Get field labels from form configuration for better display
                    field_labels = {}
                    try:
                        cur.execute("""
                            select field_name, field_label, field_type
                            from form_fields
                            where form_config_id = %s and is_active = true
                        """, (form_config_id,))
                        for field_row in cur.fetchall():
                            field_labels[field_row[0]] = {
                                'label': field_row[1],
                                'type': field_row[2]
                            }
                    except Exception:
                        pass
                    
                    # Recreate description with actual booking ID (email-friendly)
                    description_parts = [
                        "Appointment Details",
                        "",
                        f"Appointment ID: {booking_id}",
                        f"Customer: {booking.customer_name}",
                        f"Email: {booking.customer_email}",
                    ]
                    
                    if booking.customer_phone:
                        description_parts.append(f"Phone: {booking.customer_phone}")
                    
                    if resource_name:
                        description_parts.append(f"Resource/Staff: {resource_name}")
                    
                    # Add custom form fields
                    if booking.form_data:
                        description_parts.append("")
                        description_parts.append("Form Details")
                        description_parts.append("")
                        for field_name, field_value in booking.form_data.items():
                            if field_value is not None and field_value != '':
                                if field_name in field_labels:
                                    label = field_labels[field_name]['label']
                                else:
                                    label = field_name.replace('_', ' ').title()
                                
                                if isinstance(field_value, bool):
                                    display_value = '✓ Yes' if field_value else '✗ No'
                                elif isinstance(field_value, list):
                                    display_value = ', '.join(str(v) for v in field_value)
                                else:
                                    display_value = str(field_value)
                                
                                description_parts.append(f"- {label}: {display_value}")
                    
                    if booking.notes:
                        description_parts.append("")
                        description_parts.append("Additional Notes")
                        description_parts.append(f"{booking.notes}")
                    
                    description_parts.append("")
                    description_parts.append(f"Created: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                    
                    updated_description = "\n".join(description_parts)
                    
                    # Update the event description
                    cal_id_to_use = calendar_id or 'primary'
                    event = calendar_service.events().get(calendarId=cal_id_to_use, eventId=external_event_id).execute()
                    event['description'] = updated_description
                    calendar_service.events().update(calendarId=cal_id_to_use, eventId=external_event_id, body=event).execute()
                    print(f"✓ Calendar event updated successfully with Appointment ID: {booking_id}")
                except Exception as update_error:
                    print(f"⚠️ Failed to update calendar event with booking ID: {update_error}")
                    import traceback
                    traceback.print_exc()
            elif external_event_id:
                print(f"⚠️ Cannot update calendar event - service not available")
            
            return {
                "id": booking_id,
                "booking_id": booking_id,  # Also return as booking_id for clarity
                "message": f"Appointment booked successfully! Your appointment ID is: {booking_id}",
                "created_at": result[1].isoformat(),
                "status": "confirmed",
                "calendar_event_id": external_event_id,
                "calendar_synced": external_event_id is not None,
                "customer_name": booking.customer_name,
                "customer_email": booking.customer_email,
                "booking_date": str(booking.booking_date),
                "start_time": str(booking.start_time),
                "end_time": str(booking.end_time),
                "form_data": booking.form_data
            }
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()

@router.get("/bookings/{bot_id}")
def get_bookings(bot_id: str, status: Optional[str] = None, from_date: Optional[date] = None):
    """Get bookings for a bot"""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            where_clauses = ["bot_id = %s"]
            params = [bot_id]
            
            if status:
                where_clauses.append("status = %s")
                params.append(status)
            
            if from_date:
                where_clauses.append("booking_date >= %s")
                params.append(from_date)
            
            cur.execute(f"""
                select id, customer_name, customer_email, customer_phone, booking_date,
                       start_time, end_time, resource_name, form_data, status, notes, created_at
                from bookings
                where {' and '.join(where_clauses)}
                order by booking_date, start_time
            """, params)
            
            bookings = []
            for row in cur.fetchall():
                bookings.append({
                    "id": row[0],
                    "customer_name": row[1],
                    "customer_email": row[2],
                    "customer_phone": row[3],
                    "booking_date": str(row[4]),
                    "start_time": str(row[5]),
                    "end_time": str(row[6]),
                    "resource_name": row[7],
                    "form_data": row[8],
                    "status": row[9],
                    "notes": row[10],
                    "created_at": row[11].isoformat()
                })
            return {"bookings": bookings}
    finally:
        conn.close()

@router.get("/booking/{booking_id}")
def get_booking_by_id(booking_id: int):
    """Get a specific booking by ID for tracking"""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                select id, org_id, bot_id, customer_name, customer_email, customer_phone, 
                       booking_date, start_time, end_time, resource_id, resource_name, form_data, 
                       status, notes, calendar_event_id, created_at
                from bookings
                where id = %s
            """, (booking_id,))
            
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Booking not found")
            
            try:
                from datetime import datetime as _dt
                bd = row[6]
                et = row[8]
                now = _dt.now()
                end_dt = _dt.combine(bd, et)
                if end_dt <= now and (row[12] or '').lower() != 'completed':
                    with conn.cursor() as cur2:
                        cur2.execute("update bookings set status='completed', updated_at=now() where id=%s", (row[0],))
                    row = list(row)
                    row[12] = 'completed'
            except Exception:
                pass
            
            # Extract resource_name, with fallback to form_data
            resource_name = row[10]
            if not resource_name and row[11]:  # If resource_name is empty, check form_data
                try:
                    form_data = row[11] if isinstance(row[11], dict) else {}
                    # Try common field names for service/doctor
                    for field_name in ['service', 'doctor', 'service_name', 'doctor_name', 
                                       'service_type', 'appointment_type', 'resource', 
                                       'provider', 'staff', 'specialist']:
                        if field_name in form_data and form_data[field_name]:
                            resource_name = str(form_data[field_name])
                            break
                except Exception:
                    pass
            
            return {
                "id": row[0],
                "org_id": row[1],
                "bot_id": row[2],
                "customer_name": row[3],
                "customer_email": row[4],
                "customer_phone": row[5],
                "booking_date": str(row[6]),
                "start_time": str(row[7]),
                "end_time": str(row[8]),
                "resource_id": str(row[9]) if row[9] else None,
                "resource_name": resource_name,
                "form_data": row[11],
                "status": row[12],
                "notes": row[13],
                "calendar_event_id": row[14],
                "calendar_synced": row[14] is not None,
                "created_at": row[15].isoformat()
            }
    finally:
        conn.close()

class BookingRescheduleBody(BaseModel):
    org_id: str
    booking_date: date
    start_time: time
    end_time: time
    resource_id: Optional[str] = None
    form_data: Optional[Dict[str, Any]] = None

@router.post("/bookings/{booking_id}/reschedule")
def reschedule_booking(booking_id: int, body: BookingRescheduleBody):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                select bot_id, customer_name, customer_email, booking_date, start_time, end_time, status, resource_id, resource_name, calendar_event_id
                from bookings
                where id = %s
            """, (booking_id,))
            b = cur.fetchone()
            if not b:
                raise HTTPException(status_code=404, detail="Booking not found")
            bot_id, cust_name, cust_email, cur_date, cur_start, cur_end, cur_status, old_res_id, old_res_name, ext_event_id = b
            
            # Block rescheduling for cancelled appointments
            if (cur_status or '').lower() == 'cancelled':
                raise HTTPException(status_code=409, detail="Cancelled appointment cannot be rescheduled")
            
            try:
                from datetime import datetime as _dt
                now = _dt.now()
                cur_end_dt = _dt.combine(cur_date, cur_end)
                if cur_end_dt <= now:
                    with conn.cursor() as cur2:
                        cur2.execute("update bookings set status='completed', updated_at=now() where id=%s", (booking_id,))
                    conn.commit()
                    raise HTTPException(status_code=409, detail="Appointment already completed; only upcoming appointments can be rescheduled")
            except HTTPException:
                raise
            except Exception:
                pass
            
            new_res_id = body.resource_id or old_res_id
            new_res_name = old_res_name
            if new_res_id:
                cur.execute("select resource_name from booking_resources where id=%s", (new_res_id,))
                r = cur.fetchone()
                new_res_name = r[0] if r else old_res_name
            
            if new_res_id:
                cur.execute("select check_resource_capacity(%s, %s, %s, %s)", (new_res_id, body.booking_date, body.start_time, body.end_time))
                if not cur.fetchone()[0]:
                    raise HTTPException(status_code=409, detail="No capacity available for this resource and time")
            else:
                cur.execute("select check_slot_capacity(%s, %s, %s, %s)", (bot_id, body.booking_date, body.start_time, body.end_time))
                if not cur.fetchone()[0]:
                    raise HTTPException(status_code=409, detail="No capacity available for this time slot")
            
            cur.execute("""
                select timezone 
                from bot_booking_settings
                where bot_id = %s
            """, (bot_id,))
            s = cur.fetchone()
            timezone = s[0] if s and s[0] else None
            
            start_iso = f"{body.booking_date}T{body.start_time}"
            end_iso = f"{body.booking_date}T{body.end_time}"
            
            try:
                from datetime import datetime as _dt
                now_tz = _dt.now()
                if timezone:
                    try:
                        from zoneinfo import ZoneInfo as _ZoneInfo
                        now_tz = _dt.now(_ZoneInfo(timezone))
                    except Exception:
                        pass
                proposed_end = _dt.combine(body.booking_date, body.end_time)
                if timezone:
                    try:
                        from zoneinfo import ZoneInfo as _ZoneInfo
                        proposed_end = proposed_end.replace(tzinfo=_ZoneInfo(timezone))
                    except Exception:
                        pass
                if proposed_end <= now_tz:
                    raise HTTPException(status_code=409, detail="Cannot reschedule to a past time")
            except HTTPException:
                raise
            except Exception:
                pass
            
            cur.execute("select calendar_id, access_token_enc, refresh_token_enc from bot_calendar_oauth where bot_id=%s and provider='google'", (bot_id,))
            cal = cur.fetchone()
            calendar_synced = False
            if ext_event_id and cal:
                from app.services.calendar_google import _decrypt, build_service_from_tokens, update_event_oauth
                at = _decrypt(cal[1]) if cal[1] else None
                rt = _decrypt(cal[2]) if cal[2] else None
                svc = build_service_from_tokens(at or "", rt, None)
                if svc:
                    patch = {"start": {"dateTime": start_iso}, "end": {"dateTime": end_iso}}
                    ok = update_event_oauth(svc, (cal[0] or "primary"), ext_event_id, patch)
                    calendar_synced = bool(ok)
            
            # Update booking with new details including form_data if provided
            if body.form_data is not None:
                form_data_json = json.dumps(body.form_data)
                cur.execute("""
                    update bookings 
                    set booking_date=%s, start_time=%s, end_time=%s, resource_id=%s, resource_name=%s, form_data=%s, status='confirmed', updated_at=now()
                    where id=%s
                    returning id, customer_name, customer_email, booking_date, start_time, end_time, resource_id, resource_name, form_data
                """, (body.booking_date, body.start_time, body.end_time, new_res_id, new_res_name, form_data_json, booking_id))
            else:
                cur.execute("""
                    update bookings 
                    set booking_date=%s, start_time=%s, end_time=%s, resource_id=%s, resource_name=%s, status='confirmed', updated_at=now()
                    where id=%s
                    returning id, customer_name, customer_email, booking_date, start_time, end_time, resource_id, resource_name, form_data
                """, (body.booking_date, body.start_time, body.end_time, new_res_id, new_res_name, booking_id))
            upd = cur.fetchone()
            conn.commit()
            return {
                "id": upd[0],
                "customer_name": upd[1],
                "customer_email": upd[2],
                "booking_date": str(upd[3]),
                "start_time": str(upd[4]),
                "end_time": str(upd[5]),
                "resource_id": str(upd[6]) if upd[6] else None,
                "resource_name": upd[7],
                "form_data": upd[8],
                "calendar_event_id": ext_event_id,
                "calendar_synced": calendar_synced
            }
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()

# ============ Templates Endpoints ============

@router.get("/form-templates")
def get_form_templates(industry: Optional[str] = None):
    """Get available form templates"""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            where_clause = "where is_public = true"
            params = []
            
            if industry:
                where_clause += " and industry = %s"
                params.append(industry)
            
            cur.execute(f"""
                select id, name, industry, description, template_data
                from form_templates
                {where_clause}
                order by industry, name
            """, params)
            
            templates = []
            for row in cur.fetchall():
                templates.append({
                    "id": str(row[0]),
                    "name": row[1],
                    "industry": row[2],
                    "description": row[3],
                    "template_data": row[4]
                })
            return {"templates": templates}
    finally:
        conn.close()

@router.post("/form-configs/{config_id}/apply-template/{template_id}")
def apply_template_to_form(config_id: str, template_id: str):
    """Apply a template to an existing form configuration"""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            # Get template data
            cur.execute("select template_data from form_templates where id = %s", (template_id,))
            template = cur.fetchone()
            if not template:
                raise HTTPException(status_code=404, detail="Template not found")
            
            template_data = template[0]
            fields = template_data.get('fields', [])
            
            # Create fields from template
            for field in fields:
                options_json = json.dumps(field.get('options')) if field.get('options') else None
                validation_json = json.dumps(field.get('validation_rules')) if field.get('validation_rules') else None
                
                cur.execute("""
                    insert into form_fields 
                    (form_config_id, field_name, field_label, field_type, field_order, is_required,
                     placeholder, help_text, validation_rules, options, default_value)
                    values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (config_id, field.get('field_name'), field.get('field_label'), field.get('field_type'),
                      field.get('field_order', 0), field.get('is_required', False),
                      field.get('placeholder'), field.get('help_text'), validation_json, options_json,
                      field.get('default_value')))
            
            conn.commit()
            return {"success": True, "fields_created": len(fields)}
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()

class BookingCancelBody(BaseModel):
    org_id: str

@router.post("/bookings/{booking_id}/cancel")
def cancel_booking(booking_id: int, body: BookingCancelBody):
    """Cancel a booking by ID"""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            # First check if booking exists and get details
            cur.execute("""
                select id, bot_id, customer_name, customer_email, booking_date, start_time, end_time, 
                       status, calendar_event_id
                from bookings
                where id = %s and org_id = %s
            """, (booking_id, body.org_id))
            
            booking = cur.fetchone()
            if not booking:
                raise HTTPException(status_code=404, detail="Booking not found")
            
            booking_id_db, bot_id, customer_name, customer_email, booking_date, start_time, end_time, current_status, calendar_event_id = booking
            
            # Check if already cancelled
            if current_status and current_status.lower() == 'cancelled':
                return {
                    "success": True,
                    "booking_id": booking_id,
                    "message": "Appointment was already cancelled",
                    "details": {
                        "customer_name": customer_name,
                        "customer_email": customer_email,
                        "booking_date": str(booking_date),
                        "start_time": str(start_time),
                        "end_time": str(end_time),
                        "status": current_status
                    }
                }
            
            # Check if appointment is in the past
            from datetime import datetime, timezone
            import datetime as dt
            
            try:
                booking_datetime = dt.datetime.combine(booking_date, start_time)
                now = dt.datetime.now()
                
                if booking_datetime <= now:
                    # Update status to completed if in the past
                    cur.execute("""
                        update bookings 
                        set status = 'completed', updated_at = now()
                        where id = %s
                    """, (booking_id,))
                    conn.commit()
                    raise HTTPException(status_code=409, detail="Cannot cancel past appointments. This appointment has been marked as completed.")
            except HTTPException:
                raise
            except Exception:
                pass  # Continue with cancellation if date parsing fails
            
            # Try to cancel in Google Calendar if event exists
            calendar_cancelled = False
            calendar_error = None
            if calendar_event_id:
                try:
                    # Get calendar OAuth details
                    cur.execute("""
                        select calendar_id, access_token_enc, refresh_token_enc 
                        from bot_calendar_oauth 
                        where bot_id = %s and provider = 'google'
                    """, (bot_id,))
                    cal_row = cur.fetchone()
                    
                    if cal_row:
                        cal_id, at_enc, rt_enc = cal_row
                        
                        # Import calendar functions
                        from app.services.calendar_google import _decrypt, build_service_from_tokens, delete_event_oauth, refresh_access_token, _encrypt
                        
                        # Decrypt tokens
                        at = _decrypt(at_enc) if at_enc else None
                        rt = _decrypt(rt_enc) if rt_enc else None
                        
                        # Try to refresh token if needed
                        if rt and not at:
                            new_at = refresh_access_token(rt)
                            if new_at:
                                at = new_at
                                # Save the new access token
                                at_enc_new = _encrypt(new_at)
                                cur.execute("""
                                    update bot_calendar_oauth 
                                    set access_token_enc = %s, updated_at = now()
                                    where bot_id = %s and provider = 'google'
                                """, (at_enc_new, bot_id))
                                conn.commit()
                        
                        # Build service and delete event
                        if at:
                            svc = build_service_from_tokens(at, rt, None)
                            if svc:
                                success = delete_event_oauth(svc, cal_id or "primary", calendar_event_id)
                                calendar_cancelled = success
                                print(f"Calendar event deletion: {'✓' if success else '✗'} for event {calendar_event_id}")
                            else:
                                calendar_error = "Failed to build calendar service"
                        else:
                            calendar_error = "No valid access token"
                    else:
                        calendar_error = "No calendar configuration found"
                except Exception as e:
                    calendar_error = str(e)
                    print(f"Calendar cancellation failed: {e}")
                    # Don't fail the booking cancellation if calendar fails
            
            # Update booking status to cancelled
            cur.execute("""
                update bookings 
                set status = 'cancelled', cancelled_at = now(), updated_at = now()
                where id = %s
                returning id
            """, (booking_id,))
            
            result = cur.fetchone()
            if not result:
                raise HTTPException(status_code=404, detail="Failed to cancel booking")
            
            conn.commit()
            
            response = {
                "success": True,
                "booking_id": booking_id,
                "message": "Appointment cancelled successfully",
                "calendar_cancelled": calendar_cancelled,
                "details": {
                    "customer_name": customer_name,
                    "customer_email": customer_email,
                    "booking_date": str(booking_date),
                    "start_time": str(start_time),
                    "end_time": str(end_time)
                }
            }
            
            if calendar_error:
                response["calendar_warning"] = f"Calendar sync failed: {calendar_error}"
            
            return response
            
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()

@router.get("/appointment-portal/{bot_id}", response_class=HTMLResponse)
def unified_appointment_portal(bot_id: str, org_id: str, bot_key: Optional[str] = None):
    """Serve a standalone unified appointment portal (no login required)"""
    base = getattr(settings, 'PUBLIC_API_BASE_URL', '') or ''
    
    # Debug: Log the base URL being used
    print(f"[DEBUG] Appointment Portal - Using base URL: {base}")
    
    # Ensure base URL is properly formatted (no trailing slash)
    if base:
        base = base.rstrip('/')
    
    # Generate form URLs
    booking_url = f"{base}/api/form/{bot_id}?org_id={org_id}" + (f"&bot_key={bot_key}" if bot_key else "")
    reschedule_url = f"{base}/api/reschedule/{bot_id}?org_id={org_id}" + (f"&bot_key={bot_key}" if bot_key else "")
    
    html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Appointment Portal</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        .tab-content {{ display: none; }}
        .tab-content.active {{ display: block; }}
        .tab-button.active {{ 
            background-color: #3b82f6; 
            color: white; 
        }}
        .tab-button {{
            background-color: transparent;
            color: #6b7280;
            white-space: nowrap;
        }}
        .tab-button:hover {{
            background-color: #f3f4f6;
        }}
        .tab-button.active:hover {{
            background-color: #2563eb;
        }}
        
        /* Mobile responsive styles */
        @media (max-width: 640px) {{
            .tab-button {{
                font-size: 0.875rem;
                padding: 0.5rem 0.75rem;
            }}
            .tab-button span.icon {{
                display: none;
            }}
        }}
    </style>
</head>
<body class="min-h-screen bg-gray-50">
    <div class="max-w-4xl mx-auto px-4 sm:px-6 py-4 sm:py-8">
        <!-- Header -->
        <div class="text-center mb-6 sm:mb-8">
            <h1 class="text-2xl sm:text-3xl font-bold text-gray-900 mb-2">Appointment Portal</h1>
            <p class="text-sm sm:text-base text-gray-600">Book, reschedule, check status, or cancel your appointments</p>
        </div>

        <!-- Navigation Tabs -->
        <div class="flex justify-center mb-6 sm:mb-8 overflow-x-auto">
            <div class="bg-white rounded-lg p-1 shadow-sm border inline-flex">
                <div class="flex gap-1">
                    <button class="tab-button active px-3 sm:px-6 py-2 rounded-md font-medium transition-colors text-sm sm:text-base" onclick="showTab('book')">
                        <span class="icon">📅 </span>Book
                    </button>
                    <button class="tab-button px-3 sm:px-6 py-2 rounded-md font-medium transition-colors text-sm sm:text-base" onclick="showTab('reschedule')">
                        <span class="icon">🔄 </span>Reschedule
                    </button>
                    <button class="tab-button px-3 sm:px-6 py-2 rounded-md font-medium transition-colors text-sm sm:text-base" onclick="showTab('status')">
                        <span class="icon">📋 </span>Status
                    </button>
                    <button class="tab-button px-3 sm:px-6 py-2 rounded-md font-medium transition-colors text-sm sm:text-base" onclick="showTab('cancel')">
                        <span class="icon">❌ </span>Cancel
                    </button>
                </div>
            </div>
        </div>

        <!-- Content -->
        <div class="bg-white rounded-lg shadow-sm border">
            <!-- Book Tab -->
            <div id="book" class="tab-content active p-4 sm:p-8 text-center">
                <div class="max-w-md mx-auto">
                    <div class="mb-6">
                        <div class="w-14 h-14 sm:w-16 sm:h-16 mx-auto mb-4 bg-blue-100 rounded-full flex items-center justify-center">
                            <span class="text-xl sm:text-2xl">📅</span>
                        </div>
                        <h2 class="text-xl sm:text-2xl font-semibold mb-2">Book New Appointment</h2>
                        <p class="text-sm sm:text-base text-gray-600 mb-6">
                            Schedule your appointment by filling out our booking form
                        </p>
                    </div>
                    
                    <a
                        href="{booking_url}"
                        target="_blank"
                        rel="noopener noreferrer"
                        class="inline-block w-full bg-blue-600 hover:bg-blue-700 text-white font-semibold py-3 sm:py-4 px-4 sm:px-6 rounded-lg transition-colors shadow-md hover:shadow-lg text-sm sm:text-base"
                    >
                        📅 Open Booking Form
                    </a>
                    
                    <p class="text-xs sm:text-sm text-gray-500 mt-4">
                        Opens in a new window • No login required
                    </p>
                </div>
            </div>

            <!-- Reschedule Tab -->
            <div id="reschedule" class="tab-content p-4 sm:p-8 text-center">
                <div class="max-w-md mx-auto">
                    <div class="mb-6">
                        <div class="w-14 h-14 sm:w-16 sm:h-16 mx-auto mb-4 bg-orange-100 rounded-full flex items-center justify-center">
                            <span class="text-xl sm:text-2xl">🔄</span>
                        </div>
                        <h2 class="text-xl sm:text-2xl font-semibold mb-2">Reschedule Appointment</h2>
                        <p class="text-sm sm:text-base text-gray-600 mb-6">
                            Change your existing appointment to a new date and time
                        </p>
                    </div>
                    
                    <a
                        href="{reschedule_url}"
                        target="_blank"
                        rel="noopener noreferrer"
                        class="inline-block w-full bg-orange-600 hover:bg-orange-700 text-white font-semibold py-3 sm:py-4 px-4 sm:px-6 rounded-lg transition-colors shadow-md hover:shadow-lg text-sm sm:text-base"
                    >
                        🔄 Open Reschedule Form
                    </a>
                    
                    <p class="text-xs sm:text-sm text-gray-500 mt-4">
                        Opens in a new window • You will need your appointment ID
                    </p>
                </div>
            </div>

            <!-- Status Tab -->
            <div id="status" class="tab-content p-4 sm:p-6">
                <h2 class="text-lg sm:text-xl font-semibold mb-4 sm:mb-6">Check Appointment Status</h2>
                
                <div class="max-w-md mx-auto space-y-4">
                    <div>
                        <label class="block text-sm font-medium text-gray-700 mb-2">
                            Appointment ID
                        </label>
                        <input 
                            type="text"
                            id="statusAppointmentId"
                            placeholder="Enter your appointment ID (e.g., 12345)" 
                            class="w-full px-3 py-2 border border-gray-300 rounded-md text-center focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent text-sm sm:text-base"
                        />
                    </div>
                    
                    <button 
                        onclick="checkStatus()"
                        class="w-full bg-blue-600 hover:bg-blue-700 text-white font-semibold py-2.5 sm:py-2 px-4 rounded-md transition-colors text-sm sm:text-base"
                    >
                        Check Status
                    </button>

                    <div id="statusError" class="hidden p-3 bg-red-50 border border-red-200 rounded-md">
                        <p class="text-red-600 text-sm"></p>
                    </div>

                    <div id="statusResult" class="hidden mt-6 border rounded-lg">
                        <!-- Status result will be populated here -->
                    </div>
                </div>
            </div>

            <!-- Cancel Tab -->
            <div id="cancel" class="tab-content p-4 sm:p-6">
                <h2 class="text-lg sm:text-xl font-semibold mb-4 sm:mb-6">Cancel Appointment</h2>
                
                <div class="max-w-md mx-auto space-y-4">
                    <div class="bg-red-50 border border-red-200 rounded-md p-3 sm:p-4 mb-4">
                        <p class="text-red-800 text-xs sm:text-sm">
                            ⚠️ <strong>Warning:</strong> Cancelling an appointment cannot be undone. 
                            Please make sure you have the correct appointment ID.
                        </p>
                    </div>

                    <div>
                        <label class="block text-sm font-medium text-gray-700 mb-2">
                            Appointment ID
                        </label>
                        <input 
                            type="text"
                            id="cancelAppointmentId"
                            placeholder="Enter your appointment ID (e.g., 12345)" 
                            class="w-full px-3 py-2 border border-gray-300 rounded-md text-center focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent text-sm sm:text-base"
                        />
                    </div>
                    
                    <button 
                        onclick="cancelAppointment()"
                        class="w-full bg-red-600 hover:bg-red-700 text-white font-semibold py-2.5 sm:py-2 px-4 rounded-md transition-colors text-sm sm:text-base"
                    >
                        Cancel Appointment
                    </button>

                    <div id="cancelError" class="hidden p-3 bg-red-50 border border-red-200 rounded-md">
                        <p class="text-red-600 text-sm"></p>
                    </div>

                    <div id="cancelResult" class="hidden p-3 bg-green-50 border border-green-200 rounded-md">
                        <p class="text-green-600 text-sm"></p>
                    </div>
                </div>
            </div>
        </div>

        <!-- Footer -->
        <div class="text-center mt-6 sm:mt-8 text-xs sm:text-sm text-gray-500 px-4">
            <p>Need help? Contact our support team for assistance.</p>
        </div>
    </div>

    <script>
        const API_BASE = '{base}'.replace(/\/$/, '') || window.location.origin;
        const ORG_ID = '{org_id}';
        const BOT_KEY = '{bot_key or ""}';

        function showTab(tabName) {{
            // Hide all tabs
            document.querySelectorAll('.tab-content').forEach(tab => {{
                tab.classList.remove('active');
            }});
            
            // Remove active class from all buttons
            document.querySelectorAll('.tab-button').forEach(btn => {{
                btn.classList.remove('active');
            }});
            
            // Show selected tab
            document.getElementById(tabName).classList.add('active');
            
            // Add active class to clicked button
            event.target.classList.add('active');
        }}

        async function checkStatus() {{
            const appointmentId = document.getElementById('statusAppointmentId').value.trim();
            const errorDiv = document.getElementById('statusError');
            const resultDiv = document.getElementById('statusResult');
            
            // Clear previous results
            errorDiv.classList.add('hidden');
            resultDiv.classList.add('hidden');
            
            if (!appointmentId) {{
                showError('statusError', 'Please enter an appointment ID');
                return;
            }}

            try {{
                const url = `${{API_BASE}}/api/booking/${{appointmentId}}`;
                console.log('Status check URL:', url);
                const response = await fetch(url);
                
                if (!response.ok) {{
                    throw new Error('Appointment not found');
                }}

                const booking = await response.json();
                showStatusResult(booking);
            }} catch (err) {{
                console.error('Status check error:', err);
                showError('statusError', err.message || 'Failed to fetch appointment status');
            }}
        }}

        async function cancelAppointment() {{
            const appointmentId = document.getElementById('cancelAppointmentId').value.trim();
            const errorDiv = document.getElementById('cancelError');
            const resultDiv = document.getElementById('cancelResult');
            
            // Clear previous results
            errorDiv.classList.add('hidden');
            resultDiv.classList.add('hidden');
            
            if (!appointmentId) {{
                showError('cancelError', 'Please enter an appointment ID');
                return;
            }}

            if (!confirm('Are you sure you want to cancel this appointment? This action cannot be undone.')) {{
                return;
            }}

            try {{
                const url = `${{API_BASE}}/api/bookings/${{appointmentId}}/cancel`;
                console.log('Cancel URL:', url);
                const response = await fetch(url, {{
                    method: 'POST',
                    headers: {{
                        'Content-Type': 'application/json',
                    }},
                    body: JSON.stringify({{
                        org_id: ORG_ID
                    }})
                }});

                if (!response.ok) {{
                    const errorData = await response.json().catch(() => ({{}}));
                    throw new Error(errorData.detail || 'Failed to cancel appointment');
                }}

                showSuccess('cancelResult', '✅ Appointment cancelled successfully');
                document.getElementById('cancelAppointmentId').value = '';
            }} catch (err) {{
                showError('cancelError', err.message || 'Failed to cancel appointment');
            }}
        }}

        function showError(elementId, message) {{
            const errorDiv = document.getElementById(elementId);
            errorDiv.querySelector('p').textContent = message;
            errorDiv.classList.remove('hidden');
        }}

        function showSuccess(elementId, message) {{
            const successDiv = document.getElementById(elementId);
            successDiv.querySelector('p').textContent = message;
            successDiv.classList.remove('hidden');
        }}

        function showStatusResult(booking) {{
            const resultDiv = document.getElementById('statusResult');
            
            const formatDate = (dateStr) => {{
                return new Date(dateStr).toLocaleDateString('en-US', {{
                    weekday: 'long',
                    year: 'numeric',
                    month: 'long',
                    day: 'numeric'
                }});
            }};

            const formatTime = (timeStr) => {{
                return new Date(`2000-01-01T${{timeStr}}`).toLocaleTimeString('en-US', {{
                    hour: 'numeric',
                    minute: '2-digit',
                    hour12: true
                }});
            }};

            const getStatusColor = (status) => {{
                switch (status?.toLowerCase()) {{
                    case 'confirmed': return 'text-green-600 bg-green-50';
                    case 'cancelled': return 'text-red-600 bg-red-50';
                    case 'completed': return 'text-blue-600 bg-blue-50';
                    case 'pending': return 'text-yellow-600 bg-yellow-50';
                    default: return 'text-gray-600 bg-gray-50';
                }}
            }};

            resultDiv.innerHTML = `
                <div class="p-4">
                    <div class="flex items-center justify-between mb-4">
                        <h3 class="text-lg font-semibold">Appointment Details</h3>
                        <span class="px-3 py-1 rounded-full text-xs font-medium ${{getStatusColor(booking.status)}}">
                            ${{booking.status?.toUpperCase()}}
                        </span>
                    </div>
                    <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div>
                            <p class="text-sm text-gray-600">Appointment ID</p>
                            <p class="font-semibold">#${{booking.id}}</p>
                        </div>
                        <div>
                            <p class="text-sm text-gray-600">Customer</p>
                            <p class="font-semibold">${{booking.customer_name}}</p>
                        </div>
                        <div>
                            <p class="text-sm text-gray-600">Date</p>
                            <p class="font-semibold">${{formatDate(booking.booking_date)}}</p>
                        </div>
                        <div>
                            <p class="text-sm text-gray-600">Time</p>
                            <p class="font-semibold">
                                ${{formatTime(booking.start_time)}} - ${{formatTime(booking.end_time)}}
                            </p>
                        </div>
                        ${{booking.resource_name ? `
                        <div>
                            <p class="text-sm text-gray-600">Service/Provider</p>
                            <p class="font-semibold">${{booking.resource_name}}</p>
                        </div>
                        ` : ''}}
                        <div>
                            <p class="text-sm text-gray-600">Contact</p>
                            <p class="font-semibold">${{booking.customer_email}}</p>
                            ${{booking.customer_phone ? `<p class="text-sm text-gray-500">${{booking.customer_phone}}</p>` : ''}}
                        </div>
                    </div>
                    <div class="pt-4 border-t mt-4">
                        <p class="text-xs text-gray-500">
                            Booked on ${{new Date(booking.created_at).toLocaleDateString()}}
                        </p>
                    </div>
                </div>
            `;
            
            resultDiv.classList.remove('hidden');
        }}
    </script>
</body>
</html>
    """
    
    return html