package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.node.ObjectNode;

/** cp11 shares-household, UPDATED by cp28: household members still share a householdId, and the
 *  identityKey is exactly telephone|email|householdId (email empty here). */
@Tag("cp11")
class Cp11Tests extends AcceptanceBase {

	@Test
	void coreSharedHouseholdAndIdentityKey() throws Exception {
		ObjectNode a = ownerNode();
		a.put("sharesHousehold", true);
		int ida = createOwnerOk(a);
		ObjectNode b = ownerNode();
		b.put("lastName", a.get("lastName").asText());
		b.put("address", a.get("address").asText());
		b.put("sharesHousehold", true);
		int idb = createOwnerOk(b);
		JsonNode ra = fetchOwner(ida);
		JsonNode rb = fetchOwner(idb);
		assertEquals(ra.get("householdId").asText(), rb.get("householdId").asText());
		assertEquals(rb.get("telephone").asText() + "||" + rb.get("householdId").asText(),
				rb.get("identityKey").asText());
	}
}
