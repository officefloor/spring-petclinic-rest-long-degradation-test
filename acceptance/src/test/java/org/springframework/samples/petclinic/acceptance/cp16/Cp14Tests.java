package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.node.ObjectNode;

/** cp14 membership-number, UPDATED by cp16: still '<customerCode>-M<YY>', now over the city-prefixed
 *  customerCode. Recomputed from the returned fields, so format-agnostic and exact. */
@Tag("cp14")
class Cp14Tests extends AcceptanceBase {

	@Test
	void coreMembershipNumberOnNewCode() throws Exception {
		ObjectNode o = ownerNode();
		o.put("city", "Sydney");
		JsonNode r = fetchOwner(createOwnerOk(o));
		String yy = r.get("registrationDate").asText().substring(2, 4);
		assertEquals(r.get("customerCode").asText() + "-M" + yy, r.get("membershipNumber").asText());
	}
}
