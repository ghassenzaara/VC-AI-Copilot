"""FastAPI Main Application

Provides REST API endpoints for the VC Intelligence system.
"""

import logging
from contextlib import asynccontextmanager
from typing import List, Optional

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.pipeline.coordinator import PipelineCoordinator
from src.pipeline.similarity import SimilarityComputer
from src.pipeline.geocoding import get_geocoding_service
from src.database.postgres import get_postgres_connection
from src.database.neo4j_client import get_neo4j_driver


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# Global pipeline coordinator
pipeline: Optional[PipelineCoordinator] = None
similarity_computer: Optional[SimilarityComputer] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager for FastAPI app"""
    global pipeline, similarity_computer
    
    # Startup
    logger.info("Starting VC Intelligence API...")
    
    try:
        # Initialize pipeline
        pipeline = PipelineCoordinator()
        logger.info("Pipeline coordinator initialized")
        
        # Initialize similarity computer
        postgres = get_postgres_connection()
        neo4j = get_neo4j_driver()
        similarity_computer = SimilarityComputer(
            postgres_client=postgres,
            neo4j_client=neo4j
        )
        logger.info("Similarity computer initialized")
        
        logger.info("✅ API startup complete")
        
    except Exception as e:
        logger.error(f"Failed to initialize API: {e}")
        raise
    
    yield
    
    # Shutdown
    logger.info("Shutting down VC Intelligence API...")
    if pipeline:
        pipeline.close()
    logger.info("API shutdown complete")


# Create FastAPI app
app = FastAPI(
    title="VC Intelligence API",
    description="Knowledge graph and intelligence platform for venture capital deal flow",
    version="1.0.0",
    lifespan=lifespan
)


# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================
# REQUEST/RESPONSE MODELS
# ============================================

class ProcessCompanyRequest(BaseModel):
    """Request to process a single company"""
    company_domain: str
    limit_per_source: int = 100


class ProcessCompaniesRequest(BaseModel):
    """Request to process multiple companies"""
    company_domains: Optional[List[str]] = None
    limit_per_source: int = 100


class CompanySimilarityRequest(BaseModel):
    """Request to compute similarities"""
    company_id: str
    threshold: float = 0.75
    limit: int = 10


class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    version: str
    components: dict


# ============================================
# HEALTH & STATUS ENDPOINTS
# ============================================

@app.get("/", response_model=HealthResponse)
async def root():
    """Root endpoint with API info"""
    return {
        "status": "healthy",
        "version": "1.0.0",
        "components": pipeline.get_pipeline_status() if pipeline else {}
    }


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    if not pipeline:
        raise HTTPException(status_code=503, detail="Pipeline not initialized")
    
    return {
        "status": "healthy",
        "version": "1.0.0",
        "components": pipeline.get_pipeline_status()
    }


@app.get("/status")
async def get_status():
    """Get detailed pipeline status"""
    if not pipeline:
        raise HTTPException(status_code=503, detail="Pipeline not initialized")
    
    return pipeline.get_pipeline_status()


# ============================================
# PIPELINE ENDPOINTS
# ============================================

@app.post("/pipeline/process-company")
async def process_company(request: ProcessCompanyRequest, background_tasks: BackgroundTasks):
    """Process a single company through the pipeline
    
    This endpoint processes the company synchronously and returns results.
    For long-running operations, consider using background tasks.
    """
    if not pipeline:
        raise HTTPException(status_code=503, detail="Pipeline not initialized")
    
    try:
        result = pipeline.process_single_company(
            company_domain=request.company_domain,
            limit_per_source=request.limit_per_source
        )
        
        # Optionally compute similarities in background
        if similarity_computer and result.get('success') and result.get('stats', {}).get('company_id'):
            company_id = result['stats']['company_id']
            background_tasks.add_task(
                similarity_computer.compute_similarities,
                company_id=company_id
            )
        
        return result
        
    except Exception as e:
        logger.error(f"Failed to process company: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/pipeline/process-companies")
async def process_companies(request: ProcessCompaniesRequest):
    """Process multiple companies through the pipeline
    
    If company_domains is None, processes all companies.
    """
    if not pipeline:
        raise HTTPException(status_code=503, detail="Pipeline not initialized")
    
    try:
        if request.company_domains:
            results = pipeline.process_company_list(
                company_domains=request.company_domains,
                limit_per_source=request.limit_per_source
            )
        else:
            results = pipeline.process_all_companies(
                limit_per_source=request.limit_per_source
            )
        
        return {
            "total": len(results),
            "successful": sum(1 for r in results if r.get('success')),
            "results": results
        }
        
    except Exception as e:
        logger.error(f"Failed to process companies: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# SIMILARITY ENDPOINTS
# ============================================

@app.post("/similarity/compute")
async def compute_similarity(request: CompanySimilarityRequest):
    """Compute similarities for a company"""
    if not similarity_computer:
        raise HTTPException(status_code=503, detail="Similarity computer not initialized")
    
    try:
        similar = similarity_computer.compute_similarities(
            company_id=request.company_id,
            threshold=request.threshold,
            limit=request.limit
        )
        
        return {
            "company_id": request.company_id,
            "similar_companies": similar
        }
        
    except Exception as e:
        logger.error(f"Failed to compute similarities: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/similarity/compute-all")
async def compute_all_similarities(threshold: float = 0.75, limit: int = 10):
    """Compute similarities for all companies"""
    if not similarity_computer:
        raise HTTPException(status_code=503, detail="Similarity computer not initialized")
    
    try:
        stats = similarity_computer.compute_all_similarities(
            threshold=threshold,
            limit=limit
        )
        
        return stats
        
    except Exception as e:
        logger.error(f"Failed to compute all similarities: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# GEOCODING ENDPOINTS
# ============================================

@app.get("/geocode")
async def geocode_location(location: str):
    """Geocode a location string"""
    geocoding = get_geocoding_service()
    
    coords = geocoding.geocode(location)
    
    if not coords:
        raise HTTPException(status_code=404, detail=f"Location not found: {location}")
    
    return {
        "location": location,
        "latitude": coords[0],
        "longitude": coords[1]
    }


# ============================================
# QUERY ENDPOINTS (Future)
# ============================================

@app.get("/companies/{company_id}")
async def get_company(company_id: str):
    """Get company details (placeholder)"""
    # TODO: Implement company query from Neo4j
    raise HTTPException(status_code=501, detail="Not implemented yet")


@app.get("/companies")
async def list_companies(
    sector: Optional[str] = None,
    stage: Optional[str] = None,
    limit: int = 10
):
    """List companies with filters (placeholder)"""
    # TODO: Implement company listing from Neo4j
    raise HTTPException(status_code=501, detail="Not implemented yet")


# Made with Bob