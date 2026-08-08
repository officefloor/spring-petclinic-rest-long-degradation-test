package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;
import tools.jackson.databind.JsonNode;

/** membership-number: 'membershipNumber' = '&lt;customerCode&gt;-M&lt;YY&gt;', YY = last two
 * digits of the registrationDate year. Derived from the owner's own fields, so seed-independent. */
@Tag("cp14")
class Cp14Tests extends AcceptanceBase {

	@Test
	void coreMembershipNumberFormat() throws Exception {
		int id = createOwnerOk(ownerNode());
		JsonNode o = fetchOwner(id);
		String yy = o.get("registrationDate").asText().substring(2, 4);
		assertEquals(o.get("customerCode").asText() + "-M" + yy, o.get("membershipNumber").asText());
	}
}
