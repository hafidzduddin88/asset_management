# Implementation Guide: Owner GA vs IT Asset Assignment

## Overview
Sistem ini membedakan 2 tipe owner untuk asset:
- **Owner GA**: Asset berbasis lokasi (room-based) - untuk General Affairs
- **Owner IT**: Asset berbasis user assignment (user-based) - untuk IT Department

## Database Changes

### 1. Migration SQL (002_add_user_assignment.sql) ✅ UPDATED
```sql
-- Add assigned_user_id column (UUID reference)
ALTER TABLE assets 
ADD COLUMN IF NOT EXISTS assigned_user_id UUID REFERENCES auth.users(id);

-- Add assigned_user_name column (user input - will auto-resolve to assigned_user_id)
ALTER TABLE assets 
ADD COLUMN IF NOT EXISTS assigned_user_name VARCHAR(255);

-- Add owner_type column
ALTER TABLE assets 
ADD COLUMN IF NOT EXISTS owner_type VARCHAR(10) DEFAULT 'GA' CHECK (owner_type IN ('GA', 'IT'));

-- Add indexes
CREATE INDEX IF NOT EXISTS idx_assets_assigned_user ON assets(assigned_user_id);
CREATE INDEX IF NOT EXISTS idx_assets_assigned_user_name ON assets(assigned_user_name);
CREATE INDEX IF NOT EXISTS idx_assets_owner_type ON assets(owner_type);
```

**Key Points:**
- `assigned_user_name` = User input (nama user yang diketik)
- `assigned_user_id` = Auto-generated UUID (resolved dari assigned_user_name)
- System akan auto-resolve name → ID saat save

### 2. Run Migration
Jalankan SQL di Supabase SQL Editor atau via migration tool.

## Backend Changes

### 1. database_manager.py ✅ UPDATED
- ✅ Updated `get_assets_paginated()` - include assigned_user_id, assigned_user_name, owner_type
- ✅ Updated `_get_all_assets()` - include assigned_user_id, assigned_user_name, owner_type
- ✅ Updated `get_asset_by_id()` - include assigned_user_id, assigned_user_name, owner_type
- ✅ Updated `prepare_asset_data()` - auto-resolve assigned_user_id from assigned_user_name
- ✅ Auto-resolution logic: Try full_name first, then username

### 2. user_utils.py ✅ CREATED
Created new utility file with functions:
- `get_all_users()` - Get all active users for dropdown
- `get_user_by_id()` - Get user details
- `get_user_assets()` - Get assets assigned to user

### 3. assigned_user_helper.py ✅ CREATED
Helper functions for efficient user name fetching:
- `get_assigned_user_name()` - Get single user name
- `enrich_assets_with_user_names()` - Batch fetch user names for multiple assets

### 4. bulk_update.py ✅ UPDATED
- ✅ Export includes assigned_user_name column
- ✅ Import parses assigned_user_name from Excel
- ✅ Auto-resolve assigned_user_id from assigned_user_name on import
- ✅ Error handling for user not found

## Frontend Changes Needed

### 1. Add Asset Form (add.html)
Add after Owner field:

```html
<!-- Owner Type Selection -->
<div>
    <label class="block text-sm font-medium text-gray-700 required-field">Owner Type</label>
    <select name="owner_type" id="owner_type" required onchange="toggleAssignmentFields()"
        class="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-lg">
        <option value="GA">GA (Room-based)</option>
        <option value="IT">IT (User-based)</option>
    </select>
</div>

<!-- GA Fields (Location & Room) - Show by default -->
<div id="ga-fields">
    <div class="grid grid-cols-2 gap-3">
        <div>
            <label for="location_name" class="block text-sm font-medium text-gray-700 required-field">Location</label>
            <select name="location_name" id="location_name" class="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-lg">
                <option value="">Select Location</option>
                {% for location in dropdown_options.locations.keys() %}
                <option value="{{ location }}">{{ location }}</option>
                {% endfor %}
            </select>
        </div>
        <div>
            <label for="room_name" class="block text-sm font-medium text-gray-700 required-field">Room</label>
            <select name="room_name" id="room_name" class="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-lg">
                <option value="">Select Room</option>
            </select>
        </div>
    </div>
</div>

<!-- IT Fields (User Assignment) - Hidden by default -->
<div id="it-fields" style="display: none;">
    <div>
        <label for="assigned_user_name" class="block text-sm font-medium text-gray-700 required-field">Assigned To User</label>
        <input type="text" name="assigned_user_name" id="assigned_user_name" 
               list="users-list"
               placeholder="Type user name..."
               class="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-lg">
        <datalist id="users-list">
            {% for user in users %}
            <option value="{{ user.full_name }}">{{ user.username }} - {{ user.business_unit_name }}</option>
            {% endfor %}
        </datalist>
        <p class="mt-1 text-xs text-gray-500">Type user's full name or username. System will auto-resolve to user ID.</p>
    </div>
</div>

<script>
function toggleAssignmentFields() {
    const ownerType = document.getElementById('owner_type').value;
    const gaFields = document.getElementById('ga-fields');
    const itFields = document.getElementById('it-fields');
    
    if (ownerType === 'IT') {
        gaFields.style.display = 'none';
        itFields.style.display = 'block';
        // Make IT field required, GA fields optional
        document.getElementById('assigned_user_name').required = true;
        document.getElementById('location_name').required = false;
        document.getElementById('room_name').required = false;
    } else {
        gaFields.style.display = 'block';
        itFields.style.display = 'none';
        // Make GA fields required, IT field optional
        document.getElementById('assigned_user_name').required = false;
        document.getElementById('location_name').required = true;
        document.getElementById('room_name').required = true;
    }
}
</script>
```

### 2. Edit Asset Form (edit.html)
Same changes as add.html, plus pre-populate values:

```html
<select name="owner_type" id="owner_type" required onchange="toggleAssignmentFields()">
    <option value="GA" {% if asset.owner_type == 'GA' %}selected{% endif %}>GA (Room-based)</option>
    <option value="IT" {% if asset.owner_type == 'IT' %}selected{% endif %}>IT (User-based)</option>
</select>

<!-- Pre-select assigned user if exists -->
<option value="{{ user.id }}" {% if asset.assigned_user_id == user.id %}selected{% endif %}>
    {{ user.full_name }}
</option>

<script>
// On page load, show correct fields
document.addEventListener('DOMContentLoaded', function() {
    toggleAssignmentFields();
});
</script>
```

### 3. View Asset Page (view.html)
Add display logic:

```html
<!-- Location/Assignment Section -->
<div class="bg-white rounded-xl shadow-lg p-6">
    <h3 class="text-lg font-semibold text-gray-900 mb-4">
        <i class="fas fa-map-marker-alt text-purple-600 mr-2"></i>
        {% if asset.owner_type == 'IT' %}User Assignment{% else %}Location{% endif %}
    </h3>
    
    {% if asset.owner_type == 'IT' %}
        <!-- IT Asset - Show User -->
        <div class="grid grid-cols-2 gap-4">
            <div>
                <p class="text-sm text-gray-600">Assigned To</p>
                <p class="font-semibold text-gray-900">
                    {% if asset.assigned_user %}
                        {{ asset.assigned_user.full_name }}
                    {% else %}
                        Not Assigned
                    {% endif %}
                </p>
            </div>
            <div>
                <p class="text-sm text-gray-600">Username</p>
                <p class="font-semibold text-gray-900">
                    {% if asset.assigned_user %}
                        {{ asset.assigned_user.username }}
                    {% endif %}
                </p>
            </div>
            <div>
                <p class="text-sm text-gray-600">Email</p>
                <p class="font-semibold text-gray-900">
                    {% if asset.assigned_user %}
                        {{ asset.assigned_user.email }}
                    {% endif %}
                </p>
            </div>
            <div>
                <p class="text-sm text-gray-600">Business Unit</p>
                <p class="font-semibold text-gray-900">
                    {% if asset.assigned_user %}
                        {{ asset.assigned_user.business_unit_name }}
                    {% endif %}
                </p>
            </div>
        </div>
    {% else %}
        <!-- GA Asset - Show Location -->
        <div class="grid grid-cols-2 gap-4">
            <div>
                <p class="text-sm text-gray-600">Location</p>
                <p class="font-semibold text-gray-900">{{ asset.ref_locations.location_name if asset.ref_locations else 'N/A' }}</p>
            </div>
            <div>
                <p class="text-sm text-gray-600">Room</p>
                <p class="font-semibold text-gray-900">{{ asset.room_name or 'N/A' }}</p>
            </div>
        </div>
    {% endif %}
</div>
```

### 4. Asset List Page (list.html)
Update table column:

```html
<th>Location/User</th>

<!-- In table body -->
<td>
    {% if asset.owner_type == 'IT' %}
        <i class="fas fa-user text-blue-600 mr-1"></i>
        {% if asset.assigned_user %}
            {{ asset.assigned_user.full_name }}
        {% else %}
            Not Assigned
        {% endif %}
    {% else %}
        <i class="fas fa-map-marker-alt text-purple-600 mr-1"></i>
        {{ asset.ref_locations.location_name if asset.ref_locations else 'N/A' }}
    {% endif %}
</td>
```

## Route Changes Needed

### asset_management.py
Update add/edit routes to:

1. Pass users list to template:
```python
from app.utils.user_utils import get_all_users

@router.get("/asset_management/add")
async def add_asset_page(request: Request, current_profile = Depends(get_current_profile)):
    users = get_all_users()
    return templates.TemplateResponse(template_path, {
        "request": request,
        "user": current_profile,
        "dropdown_options": dropdown_options,
        "users": users  # Add this
    })
```

2. Handle owner_type in form submission:
```python
@router.post("/asset_management/add")
async def add_asset(
    request: Request,
    owner_type: str = Form(...),
    assigned_user_id: str = Form(None),
    # ... other fields
):
    asset_data = {
        "owner_type": owner_type,
        "assigned_user_id": assigned_user_id if owner_type == 'IT' else None,
        # ... other fields
    }
```

## Testing Checklist

- [ ] Run migration SQL in Supabase
- [ ] Test GA asset creation (room-based)
- [ ] Test IT asset creation (user-based)
- [ ] Test asset edit switching between GA/IT
- [ ] Test asset view showing correct info
- [ ] Test asset list displaying correctly
- [ ] Test bulk update with new fields
- [ ] Test export including owner_type and assigned_user

## Benefits

1. **Flexibility**: Support both location-based and user-based asset tracking
2. **IT Asset Management**: Track laptops, phones assigned to specific users
3. **GA Asset Management**: Track furniture, equipment in specific rooms
4. **Clear Separation**: owner_type field makes it explicit
5. **Backward Compatible**: Existing assets default to 'GA' type

## Next Steps

1. Run migration SQL
2. Update frontend templates (add.html, edit.html, view.html, list.html)
3. Update asset_management.py route
4. Test thoroughly
5. Update bulk_update.py to handle new fields
6. Update export.py to include new columns
