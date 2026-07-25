import { PrismaClient } from '@prisma/client';

// ─────────────────────────────────────────────────────────────
// AIRA Platform — Database Seed Script
// ─────────────────────────────────────────────────────────────

const prisma = new PrismaClient();

async function main() {
  console.log('🌱 Seeding AIRA database...\n');

  // ── Admin User ──────────────────────────────────────────────
  const adminUser = await prisma.user.upsert({
    where: { email: 'admin@aira.dev' },
    update: {},
    create: {
      email: 'admin@aira.dev',
      passwordHash: '$2b$12$placeholder.hash.for.seed.only',
      firstName: 'Admin',
      lastName: 'User',
      role: 'ADMIN',
      isActive: true,
      emailVerified: true,
    },
  });
  console.log(`  ✅ Admin user: ${adminUser.email} (${adminUser.id})`);

  // ── Sample User ─────────────────────────────────────────────
  const sampleUser = await prisma.user.upsert({
    where: { email: 'user@aira.dev' },
    update: {},
    create: {
      email: 'user@aira.dev',
      passwordHash: '$2b$12$placeholder.hash.for.seed.only',
      firstName: 'User',
      lastName: 'Demo',
      role: 'USER',
      isActive: true,
      emailVerified: false,
    },
  });
  console.log(`  ✅ Sample user: ${sampleUser.email} (${sampleUser.id})`);

  // ── Sample Audit Log ────────────────────────────────────────
  const auditLog = await prisma.auditLog.create({
    data: {
      userId: adminUser.id,
      action: 'SEED',
      resource: 'system',
      metadata: { message: 'Database seeded successfully' },
    },
  });
  console.log(`  ✅ Audit log: ${auditLog.action} (${auditLog.id})`);

  console.log('\n🎉 Seeding completed successfully!');
}

main()
  .catch((error) => {
    console.error('❌ Seeding failed:', error);
    process.exit(1);
  })
  .finally(async () => {
    await prisma.$disconnect();
  });
