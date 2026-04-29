-- Migration: Add user assignment for IT assets
-- This allows IT assets to be assigned to specific users instead of room locations

-- Add assigned_user_id column to assets table
ALTER TABLE assets 
ADD COLUMN IF NOT EXISTS assigned_user_id UUID REFERENCES auth.users(id);

-- Add owner_type column to differentiate GA (room-based) vs IT (user-based)
ALTER TABLE assets 
ADD COLUMN IF NOT EXISTS owner_type VARCHAR(10) DEFAULT 'GA' CHECK (owner_type IN ('GA', 'IT'));

-- Add index for better query performance
CREATE INDEX IF NOT EXISTS idx_assets_assigned_user ON assets(assigned_user_id);
CREATE INDEX IF NOT EXISTS idx_assets_owner_type ON assets(owner_type);

-- Add comment for documentation
COMMENT ON COLUMN assets.assigned_user_id IS 'For IT assets: User who is assigned this asset';
COMMENT ON COLUMN assets.owner_type IS 'GA = room-based location, IT = user-based assignment';

-- Update existing assets to have owner_type based on owner
-- Assuming 'IT' owner means IT assets, adjust as needed
UPDATE assets 
SET owner_type = 'IT' 
WHERE owner_id IN (
    SELECT owner_id FROM ref_owners WHERE owner_name = 'IT'
);

-- For IT assets without assigned user, set to NULL (will be assigned later)
-- For GA assets, assigned_user_id remains NULL (uses room_name instead)
