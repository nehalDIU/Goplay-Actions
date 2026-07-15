from typing import List, Dict, Any, Tuple
from supabase import create_client, Client, ClientOptions
from tenacity import retry, stop_after_attempt, wait_exponential, before_sleep_log
from app.models import Channel, Category
from app.logger import logger

class SupabaseImporter:
    def __init__(self, supabase_url: str, supabase_key: str, category_id: str, admin_secret_token: str = None):
        if not supabase_url or not supabase_key:
            raise ValueError("Supabase URL and Service Role Key must be provided.")
        
        headers = {}
        if admin_secret_token:
            headers["x-admin-token"] = admin_secret_token
            
        options = ClientOptions(headers=headers) if headers else None
        
        self.supabase: Client = create_client(supabase_url, supabase_key, options=options)
        self.category_id = category_id
        self.batch_size = 500

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=16),
        before_sleep=before_sleep_log(logger, 20), # 20 is logging.WARNING
        reraise=True
    )
    def verify_or_create_category(self) -> None:
        """
        Verifies if the specified category exists in the categories table.
        If it does not exist, it is created automatically.
        """
        logger.info(f"Checking if category '[sync]{self.category_id}[/sync]' exists in database...")
        
        response = self.supabase.table("categories").select("id").eq("id", self.category_id).execute()
        
        # If response.data is empty, the category doesn't exist
        if not response.data:
            logger.warning(f"Category '{self.category_id}' not found. Creating it automatically...")
            if self.category_id == "test-category":
                category = Category(
                    id=self.category_id,
                    name="Test Category",
                    sort_order=100,
                    icon="tv"
                )
            else:
                category = Category(
                    id=self.category_id,
                    name=self.category_id.replace("-", " ").title(),
                    sort_order=1,
                    icon=None
                )
            
            self.supabase.table("categories").upsert(category.to_dict()).execute()
            logger.info(f"Category '[success]{self.category_id}[/success]' successfully created.")
        else:
            logger.info(f"Category '[success]{self.category_id}[/success]' exists.")

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=16),
        before_sleep=before_sleep_log(logger, 20),
        reraise=True
    )
    def fetch_existing_channels(self) -> List[Dict[str, Any]]:
        """
        Fetches all channels in the database that belong to the target category.
        """
        logger.info(f"Fetching existing channels for category '[sync]{self.category_id}[/sync]' from Supabase...")
        response = self.supabase.table("channels").select("*").eq("category", self.category_id).execute()
        
        channels = response.data if response.data else []
        logger.info(f"Retrieved [parse]{len(channels)}[/parse] existing channels from database.")
        return channels

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=16),
        before_sleep=before_sleep_log(logger, 20),
        reraise=True
    )
    def _execute_batch_upsert(self, batch: List[Dict[str, Any]]) -> None:
        """
        Performs the actual upsert for a single batch.
        """
        self.supabase.table("channels").upsert(batch).execute()

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=16),
        before_sleep=before_sleep_log(logger, 20),
        reraise=True
    )
    def _execute_batch_delete(self, batch_ids: List[str]) -> None:
        """
        Performs the actual delete for a single batch of IDs.
        """
        self.supabase.table("channels").delete().in_("id", batch_ids).execute()

    def sync_channels(self, local_channels: List[Channel]) -> Tuple[int, int, int]:
        """
        Compares local parsed channels with remote database channels.
        Upserts new/changed channels and deletes missing channels in batches of 500.
        Returns:
            Tuple of (inserted_count, updated_count, deleted_count)
        """
        existing_channels = self.fetch_existing_channels()
        existing_map = {ch["id"]: ch for ch in existing_channels}

        to_upsert: List[Dict[str, Any]] = []
        inserted_count = 0
        updated_count = 0

        # 1. Identify Inserts and Updates
        for local_ch in local_channels:
            local_dict = local_ch.to_dict()
            
            if local_ch.id not in existing_map:
                to_upsert.append(local_dict)
                inserted_count += 1
            else:
                existing_ch = existing_map[local_ch.id]
                
                # Check for changes in key attributes
                changed = False
                for key, val in local_dict.items():
                    # Special check for nested dict comparison (like headers)
                    if existing_ch.get(key) != val:
                        changed = True
                        break
                
                if changed:
                    to_upsert.append(local_dict)
                    updated_count += 1

        # 2. Identify Deletes
        local_ids = {ch.id for ch in local_channels}
        to_delete: List[str] = [
            ch["id"] for ch in existing_channels if ch["id"] not in local_ids
        ]
        deleted_count = len(to_delete)

        # 3. Execute Deletes
        if to_delete:
            logger.info(f"Deleting {deleted_count} outdated channels from database...")
            for i in range(0, len(to_delete), self.batch_size):
                batch_ids = to_delete[i:i + self.batch_size]
                logger.debug(f"Deleting batch of {len(batch_ids)} channels...")
                self._execute_batch_delete(batch_ids)
            logger.info(f"[success]Deleted {deleted_count} channels successfully.[/success]")
        else:
            logger.info("No outdated channels to delete.")

        # 4. Execute Upserts (Inserts + Updates)
        if to_upsert:
            total_upsert = len(to_upsert)
            logger.info(f"Upserting {total_upsert} new/updated channels in batches of {self.batch_size}...")
            for i in range(0, total_upsert, self.batch_size):
                batch = to_upsert[i:i + self.batch_size]
                logger.debug(f"Upserting batch of {len(batch)} channels...")
                self._execute_batch_upsert(batch)
            logger.info(f"[success]Upserted {total_upsert} channels successfully (Inserted: {inserted_count}, Updated: {updated_count}).[/success]")
        else:
            logger.info("No new or updated channels to upsert.")

        return inserted_count, updated_count, deleted_count
