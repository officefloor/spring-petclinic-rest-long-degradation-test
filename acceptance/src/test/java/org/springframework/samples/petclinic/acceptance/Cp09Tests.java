package org.springframework.samples.petclinic.acceptance;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

/** cp09: sequential membershipNumber = current owner count + 1. */
@Tag("cp09")
class Cp09Tests extends AcceptanceBase {

	@Test
	void coreMembershipNumberIsSequential() throws Exception {
		// Absolute value depends on seed count, so assert the invariant: two
		// consecutive creations differ by exactly one.
		int a = fetchOwner(createOwnerOk(ownerNode())).get("membershipNumber").asInt();
		int b = fetchOwner(createOwnerOk(ownerNode())).get("membershipNumber").asInt();
		assertEquals(a + 1, b, "membershipNumber should increment by one per owner");
	}
}
