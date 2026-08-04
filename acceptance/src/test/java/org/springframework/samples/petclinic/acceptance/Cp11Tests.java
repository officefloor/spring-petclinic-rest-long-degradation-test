package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assertions.assertEquals;
import tools.jackson.databind.node.ObjectNode;

/** cp11 shares-household: The request may set boolean 'sharesHousehold'. When true, allow an owner at an address alr... */
@Tag("cp11")
class Cp11Tests extends AcceptanceBase {

	@Test
	void coreJoinersShareHouseholdId() throws Exception {
		ObjectNode a = ownerNode();
		createOwnerOk(a);
		ObjectNode b = ownerNode(); b.put("lastName", a.get("lastName").asText());
		b.put("address", a.get("address").asText()); b.put("sharesHousehold", true);
		int idb = createOwnerOk(b);
		ObjectNode c = ownerNode(); c.put("lastName", a.get("lastName").asText());
		c.put("address", a.get("address").asText()); c.put("sharesHousehold", true);
		int idc = createOwnerOk(c);
		String hb = fetchOwner(idb).get("householdId").asText();
		assertEquals(hb, fetchOwner(idc).get("householdId").asText());
		assertTrue(!hb.isBlank());
	}
}
