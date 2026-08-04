package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;
import tools.jackson.databind.node.ObjectNode;

/** cp11 shares-household: UPDATED by cp12 — householdId is derived from the normalized address. */
@Tag("cp11")
class Cp11Tests extends AcceptanceBase {

	@Test
	void coreSameHouseholdIdForNormalizedEqualAddresses() throws Exception {
		ObjectNode a = ownerNode(); a.put("address", "12 Main St");
		createOwnerOk(a);
		ObjectNode b = ownerNode(); b.put("lastName", a.get("lastName").asText());
		b.put("address", "12 main street"); b.put("sharesHousehold", true);
		int idb = createOwnerOk(b);
		ObjectNode c = ownerNode(); c.put("lastName", a.get("lastName").asText());
		c.put("address", "12  MAIN  ST"); c.put("sharesHousehold", true);
		int idc = createOwnerOk(c);
		assertEquals(fetchOwner(idb).get("householdId").asText(), fetchOwner(idc).get("householdId").asText());
	}
}
