import { PrismaClient } from '@prisma/client';

/**
 * Abstract base repository providing common CRUD operations
 * with soft-delete support.
 *
 * Subclasses should specify the Prisma model name (e.g. 'user')
 * and the entity type.
 */
export abstract class BaseRepository<T> {
  constructor(
    protected prisma: PrismaClient,
    protected modelName: string,
  ) {}

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  private get model(): any {
    return (this.prisma as any)[this.modelName];
  }

  /**
   * Find a single record by ID, excluding soft-deleted records.
   */
  async findById(id: string): Promise<T | null> {
    return this.model.findFirst({
      where: { id, deletedAt: null },
    });
  }

  /**
   * Find multiple records with optional filtering, pagination, and sorting.
   */
  async findMany(params: {
    where?: Record<string, unknown>;
    skip?: number;
    take?: number;
    orderBy?: Record<string, string>;
  }): Promise<T[]> {
    return this.model.findMany({
      where: params.where,
      skip: params.skip,
      take: params.take,
      orderBy: params.orderBy,
    });
  }

  /**
   * Create a new record.
   */
  async create(data: Record<string, unknown>): Promise<T> {
    return this.model.create({ data });
  }

  /**
   * Update a record by ID.
   */
  async update(id: string, data: Record<string, unknown>): Promise<T> {
    return this.model.update({
      where: { id },
      data,
    });
  }

  /**
   * Soft-delete a record by setting its deletedAt timestamp.
   */
  async softDelete(id: string): Promise<T> {
    return this.model.update({
      where: { id },
      data: { deletedAt: new Date() },
    });
  }

  /**
   * Permanently delete a record from the database.
   */
  async hardDelete(id: string): Promise<T> {
    return this.model.delete({
      where: { id },
    });
  }

  /**
   * Count records matching the given filter.
   */
  async count(where?: Record<string, unknown>): Promise<number> {
    return this.model.count({ where });
  }
}
